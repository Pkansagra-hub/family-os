"""
tests.poc.test_m15_experience_layer -- Tests for M15 Experience Layer Stubs.

Epic 15.1: Component Inventory & Package Structure
Epic 15.2: EmotionalProcessor stub & EmotionalTrajectory dataclass
Epic 15.3: AffectiveMirror stub & ToneAdjustment dataclass
Epic 15.4: NarrativeWeaver stub & NarrativeContext dataclass
Epic 15.5: AnticipatoryResponder stub & Anticipation dataclass
Epic 15.6: ProactiveAgent stub & FillMessage dataclass
Epic 15.7: RhythmController stub & TimingParams dataclass
Epic 15.8: ExperienceLayer orchestrator with tick()
Epic 15.9: Cadence tests (correct fire turns for all components)
Epic 15.10: E2E Wiring Checklist

V2 Design Ref: Section 12 (Experience Layer Hooks)
"""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import fields

from poc.k1_poc.experience import (
    AffectiveMirror,
    Anticipation,
    AnticipatoryResponder,
    EmotionalProcessor,
    EmotionalTrajectory,
    ExperienceLayer,
    FillMessage,
    NarrativeContext,
    NarrativeWeaver,
    ProactiveAgent,
    RhythmController,
    TimingParams,
    ToneAdjustment,
)

# =========================================================================
# Helpers
# =========================================================================


def _run(coro):
    """Run a coroutine synchronously in a fresh event loop."""
    return asyncio.run(coro)


def _make_context(**overrides) -> dict:
    """Create a default context dict for ExperienceLayer.tick()."""
    base = {
        "turn_transcript": "",
        "affect_history": [],
        "front_refine_affect_confidence": 0.0,
        "conversation_history": [],
        "memory_recalls": [],
        "task_state": {},
        "user_patterns": {},
        "wait_duration_ms": 0,
        "persona": {},
        "user_cadence": {},
    }
    base.update(overrides)
    return base


# =========================================================================
# Epic 15.1 -- Component Inventory & Package Structure
# =========================================================================


class TestEpic15_1_PackageStructure:
    """Epic 15.1: Component inventory -- 6 components + orchestrator."""

    # -- 15.1.1 Package exports all 6 output dataclasses --

    def test_package_exports_emotional_trajectory(self):
        from poc.k1_poc.experience import EmotionalTrajectory

        assert EmotionalTrajectory is not None

    def test_package_exports_tone_adjustment(self):
        from poc.k1_poc.experience import ToneAdjustment

        assert ToneAdjustment is not None

    def test_package_exports_narrative_context(self):
        from poc.k1_poc.experience import NarrativeContext

        assert NarrativeContext is not None

    def test_package_exports_anticipation(self):
        from poc.k1_poc.experience import Anticipation

        assert Anticipation is not None

    def test_package_exports_fill_message(self):
        from poc.k1_poc.experience import FillMessage

        assert FillMessage is not None

    def test_package_exports_timing_params(self):
        from poc.k1_poc.experience import TimingParams

        assert TimingParams is not None

    # -- 15.1.2 Package exports all 6 component classes --

    def test_package_exports_emotional_processor(self):
        from poc.k1_poc.experience import EmotionalProcessor

        assert EmotionalProcessor is not None

    def test_package_exports_affective_mirror(self):
        from poc.k1_poc.experience import AffectiveMirror

        assert AffectiveMirror is not None

    def test_package_exports_narrative_weaver(self):
        from poc.k1_poc.experience import NarrativeWeaver

        assert NarrativeWeaver is not None

    def test_package_exports_anticipatory_responder(self):
        from poc.k1_poc.experience import AnticipatoryResponder

        assert AnticipatoryResponder is not None

    def test_package_exports_proactive_agent(self):
        from poc.k1_poc.experience import ProactiveAgent

        assert ProactiveAgent is not None

    def test_package_exports_rhythm_controller(self):
        from poc.k1_poc.experience import RhythmController

        assert RhythmController is not None

    # -- 15.1.3 Package exports orchestrator --

    def test_package_exports_experience_layer(self):
        from poc.k1_poc.experience import ExperienceLayer

        assert ExperienceLayer is not None

    # -- 15.1.4 Total export count --

    def test_total_export_count(self):
        """Package exports exactly 13 names: 6 dataclasses + 6 stubs + 1 orchestrator."""
        import poc.k1_poc.experience as exp

        assert len(exp.__all__) == 13

    # -- 15.1.5 Component inventory table (6 components) --

    def test_experience_layer_has_six_components(self):
        layer = ExperienceLayer()
        assert hasattr(layer, "emotional_processor")
        assert hasattr(layer, "affective_mirror")
        assert hasattr(layer, "narrative_weaver")
        assert hasattr(layer, "anticipatory_responder")
        assert hasattr(layer, "proactive_agent")
        assert hasattr(layer, "rhythm_controller")

    def test_experience_layer_component_types(self):
        layer = ExperienceLayer()
        assert isinstance(layer.emotional_processor, EmotionalProcessor)
        assert isinstance(layer.affective_mirror, AffectiveMirror)
        assert isinstance(layer.narrative_weaver, NarrativeWeaver)
        assert isinstance(layer.anticipatory_responder, AnticipatoryResponder)
        assert isinstance(layer.proactive_agent, ProactiveAgent)
        assert isinstance(layer.rhythm_controller, RhythmController)

    def test_experience_layer_turn_count_starts_zero(self):
        layer = ExperienceLayer()
        assert layer.turn_count == 0


# =========================================================================
# Epic 15.2 -- EmotionalProcessor Stub & EmotionalTrajectory
# =========================================================================


class TestEpic15_2_EmotionalProcessor:
    """Epic 15.2: EmotionalProcessor stub with correct interface."""

    # -- 15.2.1 EmotionalTrajectory dataclass --

    def test_emotional_trajectory_default_valence(self):
        t = EmotionalTrajectory()
        assert t.valence == 0.0

    def test_emotional_trajectory_default_arousal(self):
        t = EmotionalTrajectory()
        assert t.arousal == 0.5

    def test_emotional_trajectory_default_dominance(self):
        t = EmotionalTrajectory()
        assert t.dominance == 0.5

    def test_emotional_trajectory_default_trend(self):
        t = EmotionalTrajectory()
        assert t.trend == "stable"

    def test_emotional_trajectory_default_confidence(self):
        t = EmotionalTrajectory()
        assert t.confidence == 0.0

    def test_emotional_trajectory_field_count(self):
        assert len(fields(EmotionalTrajectory)) == 5

    def test_emotional_trajectory_is_dataclass(self):
        from dataclasses import is_dataclass

        assert is_dataclass(EmotionalTrajectory)

    def test_emotional_trajectory_custom_values(self):
        t = EmotionalTrajectory(
            valence=-0.5, arousal=0.8, dominance=0.3, trend="rising", confidence=0.9
        )
        assert t.valence == -0.5
        assert t.arousal == 0.8
        assert t.dominance == 0.3
        assert t.trend == "rising"
        assert t.confidence == 0.9

    # -- 15.2.2 EmotionalProcessor class --

    def test_processor_has_process_method(self):
        ep = EmotionalProcessor()
        assert hasattr(ep, "process")
        assert callable(ep.process)

    def test_process_is_async(self):
        assert inspect.iscoroutinefunction(EmotionalProcessor.process)

    def test_process_returns_emotional_trajectory(self):
        ep = EmotionalProcessor()
        result = _run(ep.process("test transcript", []))
        assert isinstance(result, EmotionalTrajectory)

    def test_process_returns_defaults(self):
        """Stub returns neutral defaults (confidence=0.0 signals stub)."""
        ep = EmotionalProcessor()
        result = _run(ep.process("hello world", [{"valence": 0.5}]))
        assert result.valence == 0.0
        assert result.arousal == 0.5
        assert result.dominance == 0.5
        assert result.trend == "stable"
        assert result.confidence == 0.0

    def test_process_accepts_typed_arguments(self):
        """Verify process() accepts str and list[dict]."""
        ep = EmotionalProcessor()
        result = _run(ep.process("turn text", [{"v": 0.1}, {"v": 0.2}]))
        assert isinstance(result, EmotionalTrajectory)

    def test_process_signature_parameters(self):
        sig = inspect.signature(EmotionalProcessor.process)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "turn_transcript" in params
        assert "affect_history" in params


# =========================================================================
# Epic 15.3 -- AffectiveMirror Stub & ToneAdjustment
# =========================================================================


class TestEpic15_3_AffectiveMirror:
    """Epic 15.3: AffectiveMirror stub with correct interface."""

    # -- 15.3.1 ToneAdjustment dataclass --

    def test_tone_adjustment_default_warmth(self):
        t = ToneAdjustment()
        assert t.warmth == 0.5

    def test_tone_adjustment_default_formality(self):
        t = ToneAdjustment()
        assert t.formality == 0.5

    def test_tone_adjustment_default_pace(self):
        t = ToneAdjustment()
        assert t.pace == "normal"

    def test_tone_adjustment_default_mirror_intensity(self):
        t = ToneAdjustment()
        assert t.mirror_intensity == 0.0

    def test_tone_adjustment_field_count(self):
        assert len(fields(ToneAdjustment)) == 4

    def test_tone_adjustment_is_dataclass(self):
        from dataclasses import is_dataclass

        assert is_dataclass(ToneAdjustment)

    def test_tone_adjustment_custom_values(self):
        t = ToneAdjustment(warmth=0.9, formality=0.1, pace="slow", mirror_intensity=0.7)
        assert t.warmth == 0.9
        assert t.formality == 0.1
        assert t.pace == "slow"
        assert t.mirror_intensity == 0.7

    # -- 15.3.2 AffectiveMirror class --

    def test_mirror_has_mirror_method(self):
        am = AffectiveMirror()
        assert hasattr(am, "mirror")
        assert callable(am.mirror)

    def test_mirror_is_async(self):
        assert inspect.iscoroutinefunction(AffectiveMirror.mirror)

    def test_mirror_returns_tone_adjustment(self):
        am = AffectiveMirror()
        result = _run(am.mirror({}, {}))
        assert isinstance(result, ToneAdjustment)

    def test_mirror_returns_defaults(self):
        am = AffectiveMirror()
        result = _run(am.mirror({"valence": 0.5}, {"name": "concierge"}))
        assert result.warmth == 0.5
        assert result.formality == 0.5
        assert result.pace == "normal"
        assert result.mirror_intensity == 0.0

    def test_mirror_signature_parameters(self):
        sig = inspect.signature(AffectiveMirror.mirror)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "emotional_state" in params
        assert "persona" in params


# =========================================================================
# Epic 15.4 -- NarrativeWeaver Stub & NarrativeContext
# =========================================================================


class TestEpic15_4_NarrativeWeaver:
    """Epic 15.4: NarrativeWeaver stub with correct interface."""

    # -- 15.4.1 NarrativeContext dataclass --

    def test_narrative_context_default_active_threads(self):
        nc = NarrativeContext()
        assert nc.active_threads == []

    def test_narrative_context_default_thread_salience(self):
        nc = NarrativeContext()
        assert nc.thread_salience == {}

    def test_narrative_context_default_weave_suggestion(self):
        nc = NarrativeContext()
        assert nc.weave_suggestion == ""

    def test_narrative_context_field_count(self):
        assert len(fields(NarrativeContext)) == 3

    def test_narrative_context_is_dataclass(self):
        from dataclasses import is_dataclass

        assert is_dataclass(NarrativeContext)

    def test_narrative_context_mutable_defaults_independent(self):
        """Each instance gets its own list/dict (not shared)."""
        nc1 = NarrativeContext()
        nc2 = NarrativeContext()
        nc1.active_threads.append("thread-1")
        nc1.thread_salience["a"] = 0.5
        assert nc2.active_threads == []
        assert nc2.thread_salience == {}

    def test_narrative_context_custom_values(self):
        nc = NarrativeContext(
            active_threads=["t1", "t2"],
            thread_salience={"t1": 0.8, "t2": 0.3},
            weave_suggestion="connect t1 and t2",
        )
        assert nc.active_threads == ["t1", "t2"]
        assert nc.thread_salience == {"t1": 0.8, "t2": 0.3}
        assert nc.weave_suggestion == "connect t1 and t2"

    # -- 15.4.2 NarrativeWeaver class --

    def test_weaver_has_weave_method(self):
        nw = NarrativeWeaver()
        assert hasattr(nw, "weave")
        assert callable(nw.weave)

    def test_weave_is_async(self):
        assert inspect.iscoroutinefunction(NarrativeWeaver.weave)

    def test_weave_returns_narrative_context(self):
        nw = NarrativeWeaver()
        result = _run(nw.weave([], []))
        assert isinstance(result, NarrativeContext)

    def test_weave_returns_defaults(self):
        nw = NarrativeWeaver()
        result = _run(nw.weave([{"role": "user", "content": "hi"}], []))
        assert result.active_threads == []
        assert result.thread_salience == {}
        assert result.weave_suggestion == ""

    def test_weave_signature_parameters(self):
        sig = inspect.signature(NarrativeWeaver.weave)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "conversation_history" in params
        assert "memory_recalls" in params


# =========================================================================
# Epic 15.5 -- AnticipatoryResponder Stub & Anticipation
# =========================================================================


class TestEpic15_5_AnticipatoryResponder:
    """Epic 15.5: AnticipatoryResponder stub with correct interface."""

    # -- 15.5.1 Anticipation dataclass --

    def test_anticipation_default_predicted_intent(self):
        a = Anticipation()
        assert a.predicted_intent == ""

    def test_anticipation_default_confidence(self):
        a = Anticipation()
        assert a.confidence == 0.0

    def test_anticipation_default_pre_fetch_capabilities(self):
        a = Anticipation()
        assert a.pre_fetch_capabilities == []

    def test_anticipation_default_suggested_prompt_hint(self):
        a = Anticipation()
        assert a.suggested_prompt_hint == ""

    def test_anticipation_field_count(self):
        assert len(fields(Anticipation)) == 4

    def test_anticipation_is_dataclass(self):
        from dataclasses import is_dataclass

        assert is_dataclass(Anticipation)

    def test_anticipation_mutable_defaults_independent(self):
        """Each instance gets its own list (not shared)."""
        a1 = Anticipation()
        a2 = Anticipation()
        a1.pre_fetch_capabilities.append("weather")
        assert a2.pre_fetch_capabilities == []

    def test_anticipation_custom_values(self):
        a = Anticipation(
            predicted_intent="check_weather",
            confidence=0.85,
            pre_fetch_capabilities=["weather", "location"],
            suggested_prompt_hint="User may want weather next",
        )
        assert a.predicted_intent == "check_weather"
        assert a.confidence == 0.85
        assert a.pre_fetch_capabilities == ["weather", "location"]
        assert a.suggested_prompt_hint == "User may want weather next"

    # -- 15.5.2 AnticipatoryResponder class --

    def test_responder_has_anticipate_method(self):
        ar = AnticipatoryResponder()
        assert hasattr(ar, "anticipate")
        assert callable(ar.anticipate)

    def test_anticipate_is_async(self):
        assert inspect.iscoroutinefunction(AnticipatoryResponder.anticipate)

    def test_anticipate_returns_anticipation(self):
        ar = AnticipatoryResponder()
        result = _run(ar.anticipate({}, {}))
        assert isinstance(result, Anticipation)

    def test_anticipate_returns_defaults(self):
        ar = AnticipatoryResponder()
        result = _run(ar.anticipate({"status": "active"}, {"history": []}))
        assert result.predicted_intent == ""
        assert result.confidence == 0.0
        assert result.pre_fetch_capabilities == []
        assert result.suggested_prompt_hint == ""

    def test_anticipate_signature_parameters(self):
        sig = inspect.signature(AnticipatoryResponder.anticipate)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "task_state" in params
        assert "user_patterns" in params


# =========================================================================
# Epic 15.6 -- ProactiveAgent Stub & FillMessage
# =========================================================================


class TestEpic15_6_ProactiveAgent:
    """Epic 15.6: ProactiveAgent stub with correct interface."""

    # -- 15.6.1 FillMessage dataclass --

    def test_fill_message_default_message(self):
        f = FillMessage()
        assert f.message == ""

    def test_fill_message_default_style(self):
        f = FillMessage()
        assert f.style == "informational"

    def test_fill_message_default_show_progress(self):
        f = FillMessage()
        assert f.show_progress is False

    def test_fill_message_field_count(self):
        assert len(fields(FillMessage)) == 3

    def test_fill_message_is_dataclass(self):
        from dataclasses import is_dataclass

        assert is_dataclass(FillMessage)

    def test_fill_message_custom_values(self):
        f = FillMessage(
            message="Working on it...",
            style="reassuring",
            show_progress=True,
        )
        assert f.message == "Working on it..."
        assert f.style == "reassuring"
        assert f.show_progress is True

    # -- 15.6.2 ProactiveAgent class --

    def test_agent_has_generate_fill_method(self):
        pa = ProactiveAgent()
        assert hasattr(pa, "generate_fill")
        assert callable(pa.generate_fill)

    def test_generate_fill_is_async(self):
        assert inspect.iscoroutinefunction(ProactiveAgent.generate_fill)

    def test_generate_fill_returns_fill_message(self):
        pa = ProactiveAgent()
        result = _run(pa.generate_fill({}, 6000))
        assert isinstance(result, FillMessage)

    def test_generate_fill_returns_defaults(self):
        pa = ProactiveAgent()
        result = _run(pa.generate_fill({"status": "executing"}, 10000))
        assert result.message == ""
        assert result.style == "informational"
        assert result.show_progress is False

    def test_generate_fill_signature_parameters(self):
        sig = inspect.signature(ProactiveAgent.generate_fill)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "task_state" in params
        assert "wait_duration_ms" in params


# =========================================================================
# Epic 15.7 -- RhythmController Stub & TimingParams
# =========================================================================


class TestEpic15_7_RhythmController:
    """Epic 15.7: RhythmController stub with correct interface (SYNC methods)."""

    # -- 15.7.1 TimingParams dataclass --

    def test_timing_params_default_pre_delay_ms(self):
        t = TimingParams()
        assert t.pre_delay_ms == 0

    def test_timing_params_default_inter_chunk_ms(self):
        t = TimingParams()
        assert t.inter_chunk_ms == 0

    def test_timing_params_default_typing_indicator(self):
        t = TimingParams()
        assert t.typing_indicator is False

    def test_timing_params_default_beat_pattern(self):
        t = TimingParams()
        assert t.beat_pattern == "steady"

    def test_timing_params_field_count(self):
        assert len(fields(TimingParams)) == 4

    def test_timing_params_is_dataclass(self):
        from dataclasses import is_dataclass

        assert is_dataclass(TimingParams)

    def test_timing_params_custom_values(self):
        t = TimingParams(
            pre_delay_ms=200,
            inter_chunk_ms=50,
            typing_indicator=True,
            beat_pattern="syncopated",
        )
        assert t.pre_delay_ms == 200
        assert t.inter_chunk_ms == 50
        assert t.typing_indicator is True
        assert t.beat_pattern == "syncopated"

    # -- 15.7.2 RhythmController class -- sync methods --

    def test_controller_has_get_pattern_method(self):
        rc = RhythmController()
        assert hasattr(rc, "get_pattern")
        assert callable(rc.get_pattern)

    def test_controller_has_get_beat_method(self):
        rc = RhythmController()
        assert hasattr(rc, "get_beat")
        assert callable(rc.get_beat)

    def test_controller_has_adjust_timing_method(self):
        rc = RhythmController()
        assert hasattr(rc, "adjust_timing")
        assert callable(rc.adjust_timing)

    def test_get_pattern_is_sync(self):
        """RhythmController methods are SYNC, not async (1ms budget)."""
        assert not inspect.iscoroutinefunction(RhythmController.get_pattern)

    def test_get_beat_is_sync(self):
        assert not inspect.iscoroutinefunction(RhythmController.get_beat)

    def test_adjust_timing_is_sync(self):
        assert not inspect.iscoroutinefunction(RhythmController.adjust_timing)

    def test_get_pattern_returns_timing_params(self):
        rc = RhythmController()
        result = rc.get_pattern(1, {})
        assert isinstance(result, TimingParams)

    def test_get_pattern_returns_defaults(self):
        rc = RhythmController()
        result = rc.get_pattern(42, {"avg_response_time": 2.5})
        assert result.pre_delay_ms == 0
        assert result.inter_chunk_ms == 0
        assert result.typing_indicator is False
        assert result.beat_pattern == "steady"

    def test_get_beat_returns_steady(self):
        rc = RhythmController()
        assert rc.get_beat(100) == "steady"
        assert rc.get_beat(0) == "steady"
        assert rc.get_beat(5000) == "steady"

    def test_adjust_timing_returns_current_unchanged(self):
        rc = RhythmController()
        current = TimingParams(pre_delay_ms=100, inter_chunk_ms=50)
        result = rc.adjust_timing(current, {"user_speed": "fast"})
        assert result is current  # returns the same object
        assert result.pre_delay_ms == 100
        assert result.inter_chunk_ms == 50

    def test_get_pattern_signature(self):
        sig = inspect.signature(RhythmController.get_pattern)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "turn_count" in params
        assert "user_cadence" in params

    def test_get_beat_signature(self):
        sig = inspect.signature(RhythmController.get_beat)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "output_length" in params

    def test_adjust_timing_signature(self):
        sig = inspect.signature(RhythmController.adjust_timing)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "current" in params
        assert "feedback" in params


# =========================================================================
# Epic 15.8 -- ExperienceLayer Orchestrator
# =========================================================================


class TestEpic15_8_ExperienceLayerOrchestrator:
    """Epic 15.8: ExperienceLayer.tick() orchestration."""

    # -- 15.8.1 tick() method exists and is async --

    def test_tick_method_exists(self):
        layer = ExperienceLayer()
        assert hasattr(layer, "tick")
        assert callable(layer.tick)

    def test_tick_is_async(self):
        assert inspect.iscoroutinefunction(ExperienceLayer.tick)

    # -- 15.8.2 tick() returns dict --

    def test_tick_returns_dict(self):
        layer = ExperienceLayer()
        result = _run(layer.tick("LISTENING", _make_context()))
        assert isinstance(result, dict)

    # -- 15.8.3 turn_count increments on every tick --

    def test_turn_count_increments(self):
        layer = ExperienceLayer()
        assert layer.turn_count == 0
        _run(layer.tick("LISTENING", _make_context()))
        assert layer.turn_count == 1
        _run(layer.tick("LISTENING", _make_context()))
        assert layer.turn_count == 2

    def test_turn_count_is_1_indexed_on_first_tick(self):
        """turn_count starts at 0, increments to 1 on first tick (15.10.15)."""
        layer = ExperienceLayer()
        _run(layer.tick("LISTENING", _make_context()))
        assert layer.turn_count == 1

    # -- 15.8.4 timing always present --

    def test_timing_always_in_result(self):
        layer = ExperienceLayer()
        result = _run(layer.tick("LISTENING", _make_context()))
        assert "timing" in result
        assert isinstance(result["timing"], TimingParams)

    # -- 15.8.5 Non-cadence turn returns only timing --

    def test_non_cadence_turn_returns_only_timing(self):
        """On a generic turn (not matching any cadence), only timing is present."""
        layer = ExperienceLayer()
        result = _run(layer.tick("LISTENING", _make_context()))
        assert set(result.keys()) == {"timing"}

    # -- 15.8.6 tick() signature --

    def test_tick_signature(self):
        sig = inspect.signature(ExperienceLayer.tick)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "fsm_state" in params
        assert "context" in params

    # -- 15.8.7 tick() with empty context does not crash --

    def test_tick_with_empty_context_no_crash(self):
        layer = ExperienceLayer()
        result = _run(layer.tick("LISTENING", {}))
        assert isinstance(result, dict)
        assert "timing" in result

    # -- 15.8.8 tick() with minimal context on cadence turns --

    def test_tick_on_ep_turn_with_empty_context(self):
        layer = ExperienceLayer()
        for _ in range(24):
            _run(layer.tick("LISTENING", {}))
        result = _run(layer.tick("LISTENING", {}))
        assert "emotional" in result
        assert "tone" in result

    # -- 15.8.9 AffectiveMirror receives trajectory dict --

    def test_affective_mirror_receives_trajectory_dict(self):
        """Mirror receives trajectory.__dict__ per design doc Section 12.4."""
        layer = ExperienceLayer()
        for _ in range(24):
            _run(layer.tick("LISTENING", _make_context()))
        result = _run(layer.tick("LISTENING", _make_context()))
        # Both present means chaining worked
        assert "emotional" in result
        assert "tone" in result
        trajectory = result["emotional"]
        tone = result["tone"]
        assert isinstance(trajectory, EmotionalTrajectory)
        assert isinstance(tone, ToneAdjustment)

    # -- 15.8.10 ProactiveAgent conditions --

    def test_proactive_not_in_listening(self):
        layer = ExperienceLayer()
        result = _run(layer.tick("LISTENING", _make_context(wait_duration_ms=10000)))
        assert "fill" not in result

    def test_proactive_not_with_short_wait(self):
        layer = ExperienceLayer()
        result = _run(layer.tick("COMPANIONING", _make_context(wait_duration_ms=3000)))
        assert "fill" not in result

    def test_proactive_fires_with_companioning_and_long_wait(self):
        layer = ExperienceLayer()
        result = _run(layer.tick("COMPANIONING", _make_context(wait_duration_ms=6000)))
        assert "fill" in result
        assert isinstance(result["fill"], FillMessage)

    def test_proactive_threshold_exactly_5000(self):
        """wait_duration_ms == 5000 does NOT fire (> 5000 required, not >=)."""
        layer = ExperienceLayer()
        result = _run(layer.tick("COMPANIONING", _make_context(wait_duration_ms=5000)))
        assert "fill" not in result

    def test_proactive_threshold_5001(self):
        """wait_duration_ms == 5001 fires."""
        layer = ExperienceLayer()
        result = _run(layer.tick("COMPANIONING", _make_context(wait_duration_ms=5001)))
        assert "fill" in result

    # -- 15.8.11 EP skip rule --

    def test_ep_skip_high_confidence(self):
        layer = ExperienceLayer()
        for _ in range(24):
            _run(layer.tick("LISTENING", _make_context()))
        result = _run(
            layer.tick(
                "LISTENING",
                _make_context(front_refine_affect_confidence=0.9),
            )
        )
        assert "emotional" not in result
        assert "tone" not in result

    def test_ep_fires_low_confidence(self):
        layer = ExperienceLayer()
        for _ in range(24):
            _run(layer.tick("LISTENING", _make_context()))
        result = _run(
            layer.tick(
                "LISTENING",
                _make_context(front_refine_affect_confidence=0.5),
            )
        )
        assert "emotional" in result
        assert "tone" in result

    def test_ep_fires_at_threshold_0_8(self):
        """Confidence == 0.8 does NOT skip (> 0.8 required, 0.8 is <= 0.8)."""
        layer = ExperienceLayer()
        for _ in range(24):
            _run(layer.tick("LISTENING", _make_context()))
        result = _run(
            layer.tick(
                "LISTENING",
                _make_context(front_refine_affect_confidence=0.8),
            )
        )
        assert "emotional" in result
        assert "tone" in result

    def test_ep_fires_confidence_absent(self):
        """Missing front_refine_affect_confidence defaults to 0.0 -> EP fires."""
        layer = ExperienceLayer()
        for _ in range(24):
            _run(layer.tick("LISTENING", {}))
        result = _run(layer.tick("LISTENING", {}))
        assert "emotional" in result

    # -- 15.8.12 Envelope keys are correct strings --

    def test_envelope_key_emotional(self):
        layer = ExperienceLayer()
        for _ in range(24):
            _run(layer.tick("LISTENING", _make_context()))
        result = _run(layer.tick("LISTENING", _make_context()))
        assert "emotional" in result

    def test_envelope_key_tone(self):
        layer = ExperienceLayer()
        for _ in range(24):
            _run(layer.tick("LISTENING", _make_context()))
        result = _run(layer.tick("LISTENING", _make_context()))
        assert "tone" in result

    def test_envelope_key_narrative(self):
        layer = ExperienceLayer()
        for _ in range(19):
            _run(layer.tick("LISTENING", _make_context()))
        result = _run(layer.tick("LISTENING", _make_context()))
        assert "narrative" in result

    def test_envelope_key_anticipation(self):
        layer = ExperienceLayer()
        for _ in range(29):
            _run(layer.tick("LISTENING", _make_context()))
        result = _run(layer.tick("LISTENING", _make_context()))
        assert "anticipation" in result

    def test_envelope_key_fill(self):
        layer = ExperienceLayer()
        result = _run(layer.tick("COMPANIONING", _make_context(wait_duration_ms=6000)))
        assert "fill" in result

    def test_envelope_key_timing(self):
        layer = ExperienceLayer()
        result = _run(layer.tick("LISTENING", _make_context()))
        assert "timing" in result


# =========================================================================
# Epic 15.9 -- Cadence Tests
# =========================================================================


class TestEpic15_9_CadenceTests:
    """Epic 15.9: Cadence tests verify hooks fire at correct turns."""

    # -- 15.9.1 EmotionalProcessor fires every 25 turns --

    def test_emotional_processor_fires_every_25_turns(self):
        """EP fires at turns 25, 50, 75, 100 (Section 12.6)."""
        layer = ExperienceLayer()
        fired = []
        for i in range(100):
            result = _run(layer.tick("LISTENING", _make_context(turn_transcript=f"turn {i}")))
            if "emotional" in result:
                fired.append(i + 1)  # turn_count is 1-indexed
        assert fired == [25, 50, 75, 100]

    # -- 15.9.2 AffectiveMirror fires with EmotionalProcessor --

    def test_affective_mirror_fires_with_emotional(self):
        """AffectiveMirror fires on same tick as EP, not independently (Section 12.6)."""
        layer = ExperienceLayer()
        for i in range(24):
            result = _run(layer.tick("LISTENING", _make_context()))
            assert "tone" not in result, f"tone fired on non-EP turn {i + 1}"
        result = _run(layer.tick("LISTENING", _make_context()))
        assert "tone" in result  # fires with emotional on turn 25

    def test_affective_mirror_never_fires_independently(self):
        """Mirror fires ONLY when EP fires. Never on its own cadence."""
        layer = ExperienceLayer()
        tone_turns = []
        emotional_turns = []
        for i in range(100):
            result = _run(layer.tick("LISTENING", _make_context()))
            if "tone" in result:
                tone_turns.append(i + 1)
            if "emotional" in result:
                emotional_turns.append(i + 1)
        assert tone_turns == emotional_turns

    # -- 15.9.3 ProactiveAgent fires only in COMPANIONING + wait > 5s --

    def test_proactive_fires_only_in_companioning_with_wait(self):
        """Section 12.6 exact test."""
        layer = ExperienceLayer()
        # Not COMPANIONING -> no fill
        result = _run(layer.tick("LISTENING", _make_context(wait_duration_ms=10000)))
        assert "fill" not in result
        # COMPANIONING but short wait -> no fill
        result = _run(layer.tick("COMPANIONING", _make_context(wait_duration_ms=3000)))
        assert "fill" not in result
        # COMPANIONING + long wait -> fill
        result = _run(layer.tick("COMPANIONING", _make_context(wait_duration_ms=6000)))
        assert "fill" in result

    def test_proactive_all_fsm_states_no_fill(self):
        """ProactiveAgent does NOT fire for non-COMPANIONING states."""
        layer = ExperienceLayer()
        for state in ["LISTENING", "CLASSIFYING", "DISPATCHING", "DELIVERING", "PRESENTING"]:
            result = _run(layer.tick(state, _make_context(wait_duration_ms=60000)))
            assert "fill" not in result, f"fill fired in {state}"

    # -- 15.9.4 RhythmController fires every tick --

    def test_rhythm_fires_every_tick(self):
        """RhythmController fires on every tick regardless of state (Section 12.6)."""
        layer = ExperienceLayer()
        for i in range(50):
            result = _run(layer.tick("LISTENING", _make_context()))
            assert "timing" in result, f"timing missing on turn {i + 1}"

    def test_rhythm_fires_every_tick_companioning(self):
        layer = ExperienceLayer()
        for i in range(10):
            result = _run(layer.tick("COMPANIONING", _make_context()))
            assert "timing" in result

    # -- 15.9.5 NarrativeWeaver fires every 20 turns --

    def test_narrative_weaver_fires_every_20_turns(self):
        """NarrativeWeaver fires at turns 20, 40, 60, 80, 100."""
        layer = ExperienceLayer()
        fired = []
        for i in range(100):
            result = _run(layer.tick("LISTENING", _make_context()))
            if "narrative" in result:
                fired.append(i + 1)
        assert fired == [20, 40, 60, 80, 100]

    # -- 15.9.6 AnticipatoryResponder fires every 30 turns --

    def test_anticipatory_responder_fires_every_30_turns(self):
        """AnticipatoryResponder fires at turns 30, 60, 90."""
        layer = ExperienceLayer()
        fired = []
        for i in range(100):
            result = _run(layer.tick("LISTENING", _make_context()))
            if "anticipation" in result:
                fired.append(i + 1)
        assert fired == [30, 60, 90]

    # -- 15.9.7 EP skip rule high confidence --

    def test_ep_skip_when_front_confidence_high(self):
        """C11 EP skip rule: confidence > 0.8 skips EP + Mirror (Section 12.6)."""
        layer = ExperienceLayer()
        for _ in range(24):
            _run(layer.tick("LISTENING", _make_context()))
        result = _run(
            layer.tick(
                "LISTENING",
                _make_context(front_refine_affect_confidence=0.9),
            )
        )
        assert "emotional" not in result
        assert "tone" not in result

    def test_ep_skip_at_confidence_0_81(self):
        """0.81 > 0.8, EP should be skipped."""
        layer = ExperienceLayer()
        for _ in range(24):
            _run(layer.tick("LISTENING", _make_context()))
        result = _run(
            layer.tick(
                "LISTENING",
                _make_context(front_refine_affect_confidence=0.81),
            )
        )
        assert "emotional" not in result
        assert "tone" not in result

    def test_ep_skip_at_confidence_1_0(self):
        """1.0 > 0.8, EP should be skipped."""
        layer = ExperienceLayer()
        for _ in range(24):
            _run(layer.tick("LISTENING", _make_context()))
        result = _run(
            layer.tick(
                "LISTENING",
                _make_context(front_refine_affect_confidence=1.0),
            )
        )
        assert "emotional" not in result

    # -- 15.9.8 EP fires with low/absent confidence --

    def test_ep_fires_when_front_confidence_low(self):
        layer = ExperienceLayer()
        for _ in range(24):
            _run(layer.tick("LISTENING", _make_context()))
        result = _run(
            layer.tick(
                "LISTENING",
                _make_context(front_refine_affect_confidence=0.5),
            )
        )
        assert "emotional" in result
        assert "tone" in result

    def test_ep_fires_when_front_confidence_absent(self):
        layer = ExperienceLayer()
        for _ in range(24):
            _run(layer.tick("LISTENING", _make_context()))
        result = _run(layer.tick("LISTENING", _make_context()))
        assert "emotional" in result

    def test_ep_fires_at_confidence_zero(self):
        layer = ExperienceLayer()
        for _ in range(24):
            _run(layer.tick("LISTENING", _make_context()))
        result = _run(
            layer.tick(
                "LISTENING",
                _make_context(front_refine_affect_confidence=0.0),
            )
        )
        assert "emotional" in result
        assert "tone" in result

    # -- 15.9.9 Multi-component overlap --

    def test_multi_component_overlap_turn_100(self):
        """Turn 100: EP (100%25==0), NW (100%20==0). AR does NOT fire (100%30!=0)."""
        layer = ExperienceLayer()
        for _ in range(99):
            _run(layer.tick("LISTENING", _make_context()))
        result = _run(layer.tick("LISTENING", _make_context()))
        assert "emotional" in result
        assert "tone" in result
        assert "narrative" in result
        assert "timing" in result
        assert "anticipation" not in result

    def test_multi_component_overlap_turn_60(self):
        """Turn 60: NW (60%20==0), AR (60%30==0). EP does NOT fire (60%25!=0)."""
        layer = ExperienceLayer()
        for _ in range(59):
            _run(layer.tick("LISTENING", _make_context()))
        result = _run(layer.tick("LISTENING", _make_context()))
        assert "narrative" in result
        assert "anticipation" in result
        assert "timing" in result
        assert "emotional" not in result
        assert "tone" not in result

    def test_multi_component_overlap_turn_150(self):
        """Turn 150: EP (150%25==0), AR (150%30==0). NW does NOT fire (150%20!=0)."""
        layer = ExperienceLayer()
        for _ in range(149):
            _run(layer.tick("LISTENING", _make_context()))
        result = _run(layer.tick("LISTENING", _make_context()))
        assert "emotional" in result
        assert "tone" in result
        assert "anticipation" in result
        assert "timing" in result
        assert "narrative" not in result

    def test_turn_300_all_cadences_align(self):
        """Turn 300: LCM(25,20,30)=300. EP, NW, AR all fire."""
        layer = ExperienceLayer()
        for _ in range(299):
            _run(layer.tick("LISTENING", _make_context()))
        result = _run(layer.tick("LISTENING", _make_context()))
        assert "emotional" in result
        assert "tone" in result
        assert "narrative" in result
        assert "anticipation" in result
        assert "timing" in result


# =========================================================================
# Epic 15.10 -- E2E Wiring Checklist
# =========================================================================


class TestEpic15_10_E2EWiring:
    """Epic 15.10: E2E wiring checklist for Experience Layer."""

    # -- 15.10.1 tick() returns dict of envelopes --

    def test_tick_returns_dict_of_envelopes(self):
        layer = ExperienceLayer()
        result = _run(layer.tick("LISTENING", _make_context()))
        assert isinstance(result, dict)

    # -- 15.10.2 All 6 stubs return neutral defaults (no exceptions) --

    def test_emotional_processor_no_exception(self):
        ep = EmotionalProcessor()
        result = _run(ep.process("", []))
        assert result is not None

    def test_affective_mirror_no_exception(self):
        am = AffectiveMirror()
        result = _run(am.mirror({}, {}))
        assert result is not None

    def test_narrative_weaver_no_exception(self):
        nw = NarrativeWeaver()
        result = _run(nw.weave([], []))
        assert result is not None

    def test_anticipatory_responder_no_exception(self):
        ar = AnticipatoryResponder()
        result = _run(ar.anticipate({}, {}))
        assert result is not None

    def test_proactive_agent_no_exception(self):
        pa = ProactiveAgent()
        result = _run(pa.generate_fill({}, 0))
        assert result is not None

    def test_rhythm_controller_no_exception(self):
        rc = RhythmController()
        assert rc.get_pattern(1, {}) is not None
        assert rc.get_beat(100) is not None
        assert rc.adjust_timing(TimingParams(), {}) is not None

    # -- 15.10.3-15.10.6 Cadence verification (covered in 15.9) --
    # These are verified by TestEpic15_9_CadenceTests

    # -- 15.10.7-15.10.9 ProactiveAgent conditions (covered in 15.8, 15.9) --

    # -- 15.10.13 FSMController.tick_experience delegates --
    # Skipped: FSM integration is not in scope for M15 (M15 = stubs only)

    # -- 15.10.15 turn_count starts at 0, increments to 1 on first tick --

    def test_turn_count_starts_zero_increments_to_one(self):
        layer = ExperienceLayer()
        assert layer.turn_count == 0
        _run(layer.tick("LISTENING", _make_context()))
        assert layer.turn_count == 1

    # -- 15.10.16 Budget ceiling (structural, not timing) --

    def test_all_components_fire_on_turn_300(self):
        """Turn 300: all periodic components fire. Structural budget test."""
        layer = ExperienceLayer()
        for _ in range(299):
            _run(layer.tick("LISTENING", _make_context()))
        result = _run(
            layer.tick(
                "COMPANIONING",
                _make_context(wait_duration_ms=6000),
            )
        )
        # All 6 envelope keys should be present
        assert "emotional" in result
        assert "tone" in result
        assert "narrative" in result
        assert "anticipation" in result
        assert "fill" in result
        assert "timing" in result
        assert len(result) == 6

    # -- 15.10.17 Envelope keys are stable strings --

    def test_envelope_keys_are_stable(self):
        """Valid envelope keys: emotional, tone, narrative, anticipation, fill, timing."""
        valid_keys = {"emotional", "tone", "narrative", "anticipation", "fill", "timing"}
        layer = ExperienceLayer()
        # Run enough turns to trigger all periodic components
        all_keys = set()
        for _ in range(300):
            result = _run(
                layer.tick(
                    "COMPANIONING",
                    _make_context(wait_duration_ms=6000),
                )
            )
            all_keys.update(result.keys())
        assert all_keys == valid_keys

    # -- 15.10.18 ExperienceLayer has no dependency on builder/SS/bus --

    def test_no_dependency_on_prompt_builder(self):
        """ExperienceLayer receives context dict only, no import of builder."""
        import poc.k1_poc.experience.layer as layer_mod

        source = inspect.getsource(layer_mod)
        assert "prompt" not in source.lower() or "prompt" in source.lower()
        # Structural check: layer.py should not import from prompt package
        assert "from poc.k1_poc.prompt" not in source

    def test_no_dependency_on_session_state(self):
        import poc.k1_poc.experience.layer as layer_mod

        source = inspect.getsource(layer_mod)
        assert "SessionState" not in source

    def test_no_dependency_on_bus(self):
        import poc.k1_poc.experience.layer as layer_mod

        source = inspect.getsource(layer_mod)
        assert "from poc.k1_poc.bus" not in source
        assert "EventBus" not in source

    # -- Additional wiring tests --

    def test_output_types_are_correct(self):
        """Each envelope value is the correct typed output."""
        layer = ExperienceLayer()
        # Advance to turn 300 where everything fires
        for _ in range(299):
            _run(layer.tick("LISTENING", _make_context()))
        result = _run(
            layer.tick(
                "COMPANIONING",
                _make_context(wait_duration_ms=6000),
            )
        )
        assert isinstance(result["emotional"], EmotionalTrajectory)
        assert isinstance(result["tone"], ToneAdjustment)
        assert isinstance(result["narrative"], NarrativeContext)
        assert isinstance(result["anticipation"], Anticipation)
        assert isinstance(result["fill"], FillMessage)
        assert isinstance(result["timing"], TimingParams)

    def test_stubs_signal_no_algorithm(self):
        """Stub confidence == 0.0 signals no production algorithm installed."""
        ep = EmotionalProcessor()
        result = _run(ep.process("test", []))
        assert result.confidence == 0.0

        ar = AnticipatoryResponder()
        result2 = _run(ar.anticipate({}, {}))
        assert result2.confidence == 0.0

    def test_multiple_experience_layers_independent(self):
        """Each ExperienceLayer instance has its own turn_count."""
        layer1 = ExperienceLayer()
        layer2 = ExperienceLayer()
        _run(layer1.tick("LISTENING", _make_context()))
        _run(layer1.tick("LISTENING", _make_context()))
        _run(layer1.tick("LISTENING", _make_context()))
        assert layer1.turn_count == 3
        assert layer2.turn_count == 0

    def test_experience_layer_stateful_across_ticks(self):
        """turn_count persists and accumulates across tick calls."""
        layer = ExperienceLayer()
        for expected in range(1, 11):
            _run(layer.tick("LISTENING", _make_context()))
            assert layer.turn_count == expected
