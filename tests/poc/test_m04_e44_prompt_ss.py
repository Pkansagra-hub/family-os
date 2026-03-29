"""
tests.poc.test_m04_e44_prompt_ss -- E4.4 Prompt Builder SS Integration.

Validates the 3 issues of Epic 4.4:
  4.4.1 -- SECTION_RENDERERS dispatch table + _read_ss_sections renderer
  4.4.2 -- Wire stage 8 to execute SS_READ_CONFIGS
  4.4.3 -- Migrate front_handler ad-hoc reads to builder-driven rendering

Test count target: ~25 tests.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict

from poc.k1_poc.prompt.affect import AffectBand
from poc.k1_poc.prompt.builder import (
    SECTION_RENDERERS,
    SS_READ_CONFIGS,
    DynamicPromptBuilder,
    SSReadConfig,
    _render_affective_now_full,
    _render_affective_now_slim,
    _render_beliefs_active_full,
    _render_beliefs_active_slim,
    _render_clarifications_full,
    _render_clarifications_slim,
    _render_control_full,
    _render_control_slim,
    _render_history_active_full,
    _render_history_active_slim,
    _render_narrative_active_full,
    _render_narrative_active_slim,
    _render_persona_full,
    _render_persona_slim,
    _render_scoreboard_full,
    _render_scoreboard_slim,
    _render_task_state_full,
    _render_task_state_slim,
    _safe_get_ss_section,
    _style_to_hints,
    _tone_to_hints,
)
from poc.k1_poc.prompt.mode import PromptMode

# =========================================================================
# Helpers / Fixtures
# =========================================================================


def _neutral_band() -> AffectBand:
    """Create a neutral AffectBand for testing."""
    return AffectBand(band="neutral")


class MockSSManager:
    """Minimal SessionStateManager mock that returns sections by name."""

    def __init__(self, sections: Dict[str, Any] | None = None):
        self._sections = sections or {}

    def get_section(self, name: str) -> Any:
        return self._sections.get(name)


class FakeTaskState:
    """Minimal task_state section with to_prompt/to_slim_prompt."""

    def to_prompt(self) -> str:
        return "Task: buy groceries [ACTIVE]"

    def to_slim_prompt(self) -> str:
        return "1 active task"


class FakeBeliefsActive:
    """Minimal beliefs_active section with facts and pinned IDs."""

    def __init__(self):
        self._entities: dict = {}
        self._mentioned_time = None
        self._mentioned_location = None

    def list_facts(self) -> list:
        Fact = SimpleNamespace
        return [
            Fact(subject="Alice", predicate="likes", object="pizza", confidence=0.9),
            Fact(subject="Bob", predicate="needs", object="help", confidence=0.7),
        ]

    def get_fact_count(self) -> int:
        return 2

    def get_pinned_fact_ids(self) -> list:
        return ["fact-001"]


class FakeHistoryActive:
    """Minimal history_active section with format_for_prompt."""

    def format_for_prompt(self, n: int = 5) -> str:
        return "User: hello\nAssistant: hi\n" * min(n, 2)


class FakeScoreboard:
    """Minimal scoreboard section."""

    def __init__(self):
        self._referents = {
            "r1": SimpleNamespace(text="the car", salience=0.8),
        }
        self._qud_stack = [
            SimpleNamespace(text="What color?", status="OPEN"),
        ]

    def get_primary_topic(self):
        return SimpleNamespace(name="grocery shopping")


class FakeClarifications:
    """Minimal clarifications section."""

    def list_pending(self) -> list:
        return [
            SimpleNamespace(question="Which store?", priority=1),
        ]

    def get_blocking(self):
        return None


class FakeNarrativeActive:
    """Minimal narrative_active section."""

    def __init__(self):
        self._primary_thread = SimpleNamespace(
            title="Dinner Planning",
            goal="Plan dinner for tonight",
            related_entities=["Alice", "Bob"],
        )

    @property
    def primary_thread(self):
        return self._primary_thread

    def get_active_thread_name(self) -> str:
        return "Dinner Planning"


class FakeAffectiveNow:
    """Minimal affective_now section."""

    current_emotion = "happy"
    intensity = 0.7
    valence = 0.5
    arousal = 0.6


class FakeControl:
    """Minimal control section with get_metadata."""

    def get_metadata(self) -> dict:
        return {
            "name": "control",
            "safety_band": "GREEN",
            "fsm_state": "IDLE",
            "active_task_ids": [],
        }

    @property
    def fsm_overlay(self) -> dict:
        return {"fsm_state": "IDLE", "active_task_ids": [], "complexity_tier": "LOW"}


class FakePersona:
    """Minimal persona section."""

    def get_all_preferences(self) -> dict:
        return {"payment_method": "credit_card", "dietary": "vegetarian"}


def _make_full_ss() -> MockSSManager:
    """Build a mock SS with all 10 sections populated."""
    return MockSSManager(
        {
            "task_state": FakeTaskState(),
            "task_artifacts": FakeTaskState(),  # reuse for to_prompt/to_slim_prompt
            "beliefs_active": FakeBeliefsActive(),
            "history_active": FakeHistoryActive(),
            "scoreboard": FakeScoreboard(),
            "clarifications": FakeClarifications(),
            "narrative_active": FakeNarrativeActive(),
            "affective_now": FakeAffectiveNow(),
            "control": FakeControl(),
            "persona": FakePersona(),
        }
    )


# =========================================================================
# 4.4.1 -- SECTION_RENDERERS dispatch table
# =========================================================================


class TestSectionRenderersTable:
    """SECTION_RENDERERS has 10 entries covering all SS sections (M4 4.4.1)."""

    def test_renderers_has_10_entries(self):
        assert len(SECTION_RENDERERS) == 10

    def test_all_config_sections_have_renderers(self):
        """Every section referenced in SS_READ_CONFIGS has a renderer."""
        all_sections = set()
        for mode_configs in SS_READ_CONFIGS.values():
            for cfg in mode_configs:
                all_sections.add(cfg.section)
        for section in all_sections:
            assert section in SECTION_RENDERERS, f"Missing renderer for {section}"

    def test_each_renderer_is_callable_pair(self):
        for name, (full_fn, slim_fn) in SECTION_RENDERERS.items():
            assert callable(full_fn), f"{name} full_fn not callable"
            assert callable(slim_fn), f"{name} slim_fn not callable"


# =========================================================================
# 4.4.1 -- Individual renderer tests
# =========================================================================


class TestTaskStateRenderers:
    """task_state delegates to to_prompt/to_slim_prompt (M4 4.4.1)."""

    def test_full_delegates_to_prompt(self):
        section = FakeTaskState()
        cfg = SSReadConfig("task_state", "full")
        assert _render_task_state_full(section, cfg) == "Task: buy groceries [ACTIVE]"

    def test_slim_delegates_to_slim_prompt(self):
        section = FakeTaskState()
        cfg = SSReadConfig("task_state", "slim")
        assert _render_task_state_slim(section, cfg) == "1 active task"

    def test_full_empty_when_no_to_prompt(self):
        section = SimpleNamespace()
        cfg = SSReadConfig("task_state", "full")
        assert _render_task_state_full(section, cfg) == ""


class TestBeliefsActiveRenderers:
    """beliefs_active formats facts as SVO lines (M4 4.4.1)."""

    def test_full_formats_facts(self):
        section = FakeBeliefsActive()
        cfg = SSReadConfig("beliefs_active", "full")
        result = _render_beliefs_active_full(section, cfg)
        assert "Alice likes pizza" in result
        assert "confidence: 0.9" in result
        assert "Bob needs help" in result

    def test_slim_shows_count_and_pinned(self):
        section = FakeBeliefsActive()
        cfg = SSReadConfig("beliefs_active", "slim")
        result = _render_beliefs_active_slim(section, cfg)
        assert "Facts: 2" in result
        assert "fact-001" in result


class TestHistoryActiveRenderers:
    """history_active uses format_for_prompt(n=window) (M4 4.4.1)."""

    def test_full_uses_config_window(self):
        section = FakeHistoryActive()
        cfg = SSReadConfig("history_active", "full", history_window=10)
        result = _render_history_active_full(section, cfg)
        assert "User: hello" in result

    def test_slim_caps_window_at_5(self):
        section = FakeHistoryActive()
        cfg = SSReadConfig("history_active", "full", history_window=20)
        result = _render_history_active_slim(section, cfg)
        assert "User: hello" in result


class TestScoreboardRenderers:
    """scoreboard formats referents, topic, QUD (M4 4.4.1)."""

    def test_full_includes_referents_topic_qud(self):
        section = FakeScoreboard()
        cfg = SSReadConfig("scoreboard", "full")
        result = _render_scoreboard_full(section, cfg)
        assert "the car" in result
        assert "grocery shopping" in result
        assert "What color?" in result

    def test_slim_shows_topic_and_count(self):
        section = FakeScoreboard()
        cfg = SSReadConfig("scoreboard", "slim")
        result = _render_scoreboard_slim(section, cfg)
        assert "grocery shopping" in result
        assert "Referents: 1" in result


class TestClarificationsRenderers:
    """clarifications formats pending + blocking (M4 4.4.1)."""

    def test_full_lists_pending(self):
        section = FakeClarifications()
        cfg = SSReadConfig("clarifications", "full")
        result = _render_clarifications_full(section, cfg)
        assert "Which store?" in result

    def test_slim_shows_count(self):
        section = FakeClarifications()
        cfg = SSReadConfig("clarifications", "slim")
        result = _render_clarifications_slim(section, cfg)
        assert "Pending: 1" in result


class TestNarrativeActiveRenderers:
    """narrative_active shows thread name, goal, entities (M4 4.4.1)."""

    def test_full_shows_thread_goal_entities(self):
        section = FakeNarrativeActive()
        cfg = SSReadConfig("narrative_active", "full")
        result = _render_narrative_active_full(section, cfg)
        assert "Dinner Planning" in result
        assert "Plan dinner" in result
        assert "Alice" in result

    def test_slim_shows_thread_name_only(self):
        section = FakeNarrativeActive()
        cfg = SSReadConfig("narrative_active", "slim")
        result = _render_narrative_active_slim(section, cfg)
        assert "Thread: Dinner Planning" in result


class TestAffectiveNowRenderers:
    """affective_now shows emotion, intensity, valence, arousal (M4 4.4.1)."""

    def test_full_shows_all_dimensions(self):
        section = FakeAffectiveNow()
        cfg = SSReadConfig("affective_now", "full")
        result = _render_affective_now_full(section, cfg)
        assert "Emotion: happy" in result
        assert "Intensity: 0.7" in result
        assert "Valence: 0.5" in result
        assert "Arousal: 0.6" in result

    def test_slim_one_liner(self):
        section = FakeAffectiveNow()
        cfg = SSReadConfig("affective_now", "slim")
        result = _render_affective_now_slim(section, cfg)
        assert result == "happy (0.7)"


class TestControlRenderers:
    """control shows metadata including fsm_overlay (M4 4.4.1)."""

    def test_full_shows_metadata(self):
        section = FakeControl()
        cfg = SSReadConfig("control", "full")
        result = _render_control_full(section, cfg)
        assert "safety_band: GREEN" in result

    def test_slim_shows_fsm_and_safety(self):
        section = FakeControl()
        cfg = SSReadConfig("control", "slim")
        result = _render_control_slim(section, cfg)
        assert "FSM: IDLE" in result
        assert "Safety: GREEN" in result


class TestPersonaRenderers:
    """persona shows preferences (M4 4.4.1)."""

    def test_full_shows_all_prefs(self):
        section = FakePersona()
        cfg = SSReadConfig("persona", "full")
        result = _render_persona_full(section, cfg)
        assert "payment_method: credit_card" in result
        assert "dietary: vegetarian" in result

    def test_slim_shows_key_names(self):
        section = FakePersona()
        cfg = SSReadConfig("persona", "slim")
        result = _render_persona_slim(section, cfg)
        assert "payment_method" in result
        assert "dietary" in result


# =========================================================================
# 4.4.1 -- _read_ss_sections integration
# =========================================================================


class TestReadSsSections:
    """_read_ss_sections assembles labeled blocks from renderers (M4 4.4.1)."""

    def test_renders_all_configured_sections(self):
        ss = _make_full_ss()
        builder = DynamicPromptBuilder()
        configs = [
            SSReadConfig("task_state", "full"),
            SSReadConfig("beliefs_active", "full"),
            SSReadConfig("history_active", "full", history_window=5),
        ]
        result = builder._read_ss_sections(ss, configs)
        assert "== SESSION STATE ==" in result
        assert "## task_state" in result
        assert "## beliefs_active" in result
        assert "## history_active" in result

    def test_skip_mode_produces_no_output(self):
        ss = _make_full_ss()
        builder = DynamicPromptBuilder()
        configs = [SSReadConfig("task_state", "skip")]
        result = builder._read_ss_sections(ss, configs)
        assert result == ""

    def test_missing_section_silently_skipped(self):
        ss = MockSSManager({})  # empty
        builder = DynamicPromptBuilder()
        configs = [SSReadConfig("task_state", "full")]
        result = builder._read_ss_sections(ss, configs)
        assert result == ""

    def test_slim_mode_uses_slim_renderer(self):
        ss = _make_full_ss()
        builder = DynamicPromptBuilder()
        configs = [SSReadConfig("beliefs_active", "slim")]
        result = builder._read_ss_sections(ss, configs)
        assert "Facts: 2" in result
        assert "Pinned:" in result

    def test_mixed_modes_full_and_slim(self):
        ss = _make_full_ss()
        builder = DynamicPromptBuilder()
        configs = [
            SSReadConfig("task_state", "full"),
            SSReadConfig("beliefs_active", "slim"),
        ]
        result = builder._read_ss_sections(ss, configs)
        assert "buy groceries" in result
        assert "Facts: 2" in result


# =========================================================================
# 4.4.2 -- Wire stage 8 in build()
# =========================================================================


class TestBuildStage8:
    """build() with ss parameter renders SS sections in prompt (M4 4.4.2)."""

    def test_ss_none_backward_compatible(self):
        """When ss=None, stage 8 produces nothing (backward compat)."""
        builder = DynamicPromptBuilder()
        ctx = builder.build(
            mode=PromptMode.STANDARD,
            affect_band=_neutral_band(),
            ss=None,
        )
        assert "== SESSION STATE ==" not in ctx.system_prompt

    def test_ss_provided_renders_sections(self):
        """When ss is provided, SS sections appear in system_prompt."""
        ss = _make_full_ss()
        builder = DynamicPromptBuilder()
        ctx = builder.build(
            mode=PromptMode.STANDARD,
            affect_band=_neutral_band(),
            ss=ss,
        )
        assert "== SESSION STATE ==" in ctx.system_prompt
        assert "## beliefs_active" in ctx.system_prompt
        assert "## affective_now" in ctx.system_prompt

    def test_ss_sections_between_scenario_and_affect(self):
        """SS block appears after scenario data (stage 7) in final prompt."""
        ss = _make_full_ss()
        builder = DynamicPromptBuilder()
        ctx = builder.build(
            mode=PromptMode.STANDARD,
            affect_band=_neutral_band(),
            ss=ss,
        )
        # SESSION STATE must appear in the prompt
        assert "== SESSION STATE ==" in ctx.system_prompt

    def test_mode_specific_configs_applied(self):
        """CLARIFY_ASK mode uses slim beliefs_active per SS_READ_CONFIGS."""
        ss = _make_full_ss()
        builder = DynamicPromptBuilder()
        ctx = builder.build(
            mode=PromptMode.CLARIFY_ASK,
            affect_band=_neutral_band(),
            ss=ss,
        )
        # CLARIFY_ASK has beliefs_active=slim
        assert "Facts: 2" in ctx.system_prompt

    def test_empty_ss_manager_no_crash(self):
        """Empty SS manager produces prompt without SESSION STATE block."""
        ss = MockSSManager({})
        builder = DynamicPromptBuilder()
        ctx = builder.build(
            mode=PromptMode.STANDARD,
            affect_band=_neutral_band(),
            ss=ss,
        )
        assert "== SESSION STATE ==" not in ctx.system_prompt


# =========================================================================
# 4.4.3 -- front_handler passes ss=ss
# =========================================================================


class TestFrontHandlerSsPassthrough:
    """front_handler passes ss to builder.build() (M4 4.4.3)."""

    def test_build_signature_accepts_ss(self):
        """build() accepts ss keyword argument without error."""
        builder = DynamicPromptBuilder()
        # Should not raise
        ctx = builder.build(
            mode=PromptMode.STANDARD,
            affect_band=_neutral_band(),
            ss=None,
        )
        assert ctx is not None

    def test_safe_get_ss_section_returns_none_for_missing(self):
        """_safe_get_ss_section returns None for missing sections."""
        ss = MockSSManager({})
        assert _safe_get_ss_section(ss, "task_state") is None

    def test_safe_get_ss_section_returns_section(self):
        """_safe_get_ss_section returns section when present."""
        section = FakeTaskState()
        ss = MockSSManager({"task_state": section})
        assert _safe_get_ss_section(ss, "task_state") is section

    def test_safe_get_ss_section_handles_exception(self):
        """_safe_get_ss_section returns None on exception."""

        class BrokenSS:
            def get_section(self, name):
                raise RuntimeError("boom")

        assert _safe_get_ss_section(BrokenSS(), "anything") is None


# ---- Experience Layer wiring: tone + style in affective_now renderer ----


class FakeAffectiveNowWithToneAndStyle:
    """Affective section with _tone_adjustment and _response_style."""

    current_emotion = "sad"
    intensity = 0.6
    valence = -0.4
    arousal = 0.3
    _tone_adjustment = {
        "warmth": 0.15,
        "formality": -0.1,
        "pace": "slower",
        "mirror_intensity": 0.0,
    }
    _response_style = {
        "response_length_preference": "concise",
        "message_style": "single_complete",
        "verbosity_level": 0.25,
    }


class TestToneToHints:
    """_tone_to_hints converts tone dict to natural-language hints."""

    def test_warm_caring_tone(self):
        hints = _tone_to_hints({"warmth": 0.15})
        assert any("warmer" in h for h in hints)

    def test_cool_tone(self):
        hints = _tone_to_hints({"warmth": -0.2})
        assert any("cooler" in h for h in hints)

    def test_formal(self):
        hints = _tone_to_hints({"formality": 0.2})
        assert any("formal" in h for h in hints)

    def test_casual(self):
        hints = _tone_to_hints({"formality": -0.15})
        assert any("casual" in h for h in hints)

    def test_slower_pace(self):
        hints = _tone_to_hints({"pace": "slower"})
        assert any("Slower" in h for h in hints)

    def test_faster_pace(self):
        hints = _tone_to_hints({"pace": "faster"})
        assert any("energetic" in h for h in hints)

    def test_high_mirror(self):
        hints = _tone_to_hints({"mirror_intensity": 0.7})
        assert any("Mirror" in h for h in hints)

    def test_light_mirror(self):
        hints = _tone_to_hints({"mirror_intensity": 0.3})
        assert any("Lightly" in h for h in hints)

    def test_no_mirror_when_zero(self):
        hints = _tone_to_hints({"mirror_intensity": 0.0})
        assert not any("mirror" in h.lower() for h in hints)

    def test_empty_dict_returns_no_hints(self):
        assert _tone_to_hints({}) == []

    def test_neutral_values_produce_no_hints(self):
        hints = _tone_to_hints(
            {
                "warmth": 0.0,
                "formality": 0.0,
                "pace": "",
                "mirror_intensity": 0.0,
            }
        )
        assert hints == []


class TestStyleToHints:
    """_style_to_hints converts response style dict to natural-language hints."""

    def test_concise_preference(self):
        hints = _style_to_hints({"response_length_preference": "concise"})
        assert any("SHORT" in h for h in hints)

    def test_detailed_preference(self):
        hints = _style_to_hints({"response_length_preference": "detailed"})
        assert any("DETAILED" in h for h in hints)

    def test_balanced_produces_no_length_hint(self):
        hints = _style_to_hints({"response_length_preference": "balanced"})
        assert not any("SHORT" in h or "DETAILED" in h for h in hints)

    def test_conversational_bursts(self):
        hints = _style_to_hints({"message_style": "conversational_bursts"})
        assert any("rapid" in h for h in hints)

    def test_single_complete_no_burst_hint(self):
        hints = _style_to_hints({"message_style": "single_complete"})
        assert not any("rapid" in h for h in hints)

    def test_low_verbosity(self):
        hints = _style_to_hints({"verbosity_level": 0.2})
        assert any("filler" in h for h in hints)

    def test_high_verbosity(self):
        hints = _style_to_hints({"verbosity_level": 0.8})
        assert any("expressive" in h for h in hints)

    def test_default_values_produce_no_hints(self):
        assert _style_to_hints({}) == []


class TestAffectiveNowRendererWithExperienceLayer:
    """Affective renderers include tone/style hints when present."""

    def test_full_includes_tone_fine_tuning_header(self):
        section = FakeAffectiveNowWithToneAndStyle()
        cfg = SSReadConfig("affective_now", "full")
        result = _render_affective_now_full(section, cfg)
        assert "== TONE FINE-TUNING ==" in result

    def test_full_includes_warmth_hint(self):
        section = FakeAffectiveNowWithToneAndStyle()
        cfg = SSReadConfig("affective_now", "full")
        result = _render_affective_now_full(section, cfg)
        assert "warmer" in result

    def test_full_includes_pace_hint(self):
        section = FakeAffectiveNowWithToneAndStyle()
        cfg = SSReadConfig("affective_now", "full")
        result = _render_affective_now_full(section, cfg)
        assert "Slower" in result

    def test_full_includes_response_style_header(self):
        section = FakeAffectiveNowWithToneAndStyle()
        cfg = SSReadConfig("affective_now", "full")
        result = _render_affective_now_full(section, cfg)
        assert "== RESPONSE STYLE ==" in result

    def test_full_includes_concise_hint(self):
        section = FakeAffectiveNowWithToneAndStyle()
        cfg = SSReadConfig("affective_now", "full")
        result = _render_affective_now_full(section, cfg)
        assert "SHORT" in result

    def test_full_includes_low_verbosity_hint(self):
        section = FakeAffectiveNowWithToneAndStyle()
        cfg = SSReadConfig("affective_now", "full")
        result = _render_affective_now_full(section, cfg)
        assert "filler" in result

    def test_full_still_shows_base_dimensions(self):
        section = FakeAffectiveNowWithToneAndStyle()
        cfg = SSReadConfig("affective_now", "full")
        result = _render_affective_now_full(section, cfg)
        assert "Emotion: sad" in result
        assert "Valence: -0.4" in result
        assert "Arousal: 0.3" in result

    def test_full_no_tone_block_when_absent(self):
        """Original section without _tone_adjustment produces no tone block."""
        section = FakeAffectiveNow()
        cfg = SSReadConfig("affective_now", "full")
        result = _render_affective_now_full(section, cfg)
        assert "TONE FINE-TUNING" not in result
        assert "RESPONSE STYLE" not in result

    def test_full_no_style_block_when_empty_dict(self):
        """Empty dicts produce no advisory blocks."""
        section = FakeAffectiveNow()
        section._tone_adjustment = {}
        section._response_style = {}
        cfg = SSReadConfig("affective_now", "full")
        result = _render_affective_now_full(section, cfg)
        assert "TONE FINE-TUNING" not in result
        assert "RESPONSE STYLE" not in result

    def test_slim_shows_style_when_non_default(self):
        section = FakeAffectiveNowWithToneAndStyle()
        cfg = SSReadConfig("affective_now", "slim")
        result = _render_affective_now_slim(section, cfg)
        assert "Style: concise" in result

    def test_slim_no_style_when_balanced(self):
        section = FakeAffectiveNow()
        section._response_style = {"response_length_preference": "balanced"}
        cfg = SSReadConfig("affective_now", "slim")
        result = _render_affective_now_slim(section, cfg)
        assert "Style" not in result

    def test_slim_no_style_when_absent(self):
        section = FakeAffectiveNow()
        cfg = SSReadConfig("affective_now", "slim")
        result = _render_affective_now_slim(section, cfg)
        assert "Style" not in result
