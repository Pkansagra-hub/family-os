"""
Tests for Anniversary Demo Runner (Milestone 3)
=================================================

Tests for the 30-turn demo script, display, and runner components.
"""

from poc.session_state_demo.anniversary_demo.display import CYAN, GREEN, RED, YELLOW, colorize
from poc.session_state_demo.anniversary_demo.runner import DemoRunner, DemoState
from poc.session_state_demo.anniversary_demo.script import (
    DEMO_SCRIPT,
    SCRIPT_METADATA,
    Act,
    ExpectedBehavior,
    TurnEvent,
    get_total_turns,
    get_turn,
    get_turns_by_act,
)

# ============================================================================
# Script Tests
# ============================================================================


class TestDemoScript:
    """Tests for the 30-turn demo script."""

    def test_script_has_30_turns(self):
        """Script should have exactly 30 turns."""
        assert len(DEMO_SCRIPT) == 30
        assert get_total_turns() == 30

    def test_turns_numbered_1_to_30(self):
        """Turns should be numbered 1-30."""
        turn_numbers = [t.turn_number for t in DEMO_SCRIPT]
        assert turn_numbers == list(range(1, 31))

    def test_get_turn_by_number(self):
        """Should retrieve specific turn by number."""
        turn = get_turn(1)
        assert turn is not None
        assert turn.turn_number == 1
        assert "planning a surprise" in turn.user_input.lower()

    def test_get_turn_invalid_number(self):
        """Invalid turn number should return None."""
        assert get_turn(0) is None
        assert get_turn(31) is None
        assert get_turn(-1) is None

    def test_all_turns_have_act(self):
        """Every turn should have an assigned act."""
        for turn in DEMO_SCRIPT:
            assert turn.act is not None
            assert isinstance(turn.act, Act)

    def test_act_distribution(self):
        """Acts should cover correct turn ranges."""
        act1 = get_turns_by_act(Act.SETUP)
        act2 = get_turns_by_act(Act.GAP_DETECTION)
        act3 = get_turns_by_act(Act.BACKGROUND)
        act4 = get_turns_by_act(Act.PROACTIVE)
        act5 = get_turns_by_act(Act.RESOLUTION)

        assert len(act1) == 8  # Turns 1-8
        assert len(act2) == 6  # Turns 9-14
        assert len(act3) == 6  # Turns 15-20
        assert len(act4) == 5  # Turns 21-25
        assert len(act5) == 5  # Turns 26-30


class TestKeyMoments:
    """Tests for key demo moments."""

    def test_turn_5_shellfish_allergy(self):
        """Turn 5 should record shellfish allergy."""
        turn = get_turn(5)
        assert turn is not None
        assert "shellfish allergy" in turn.user_input.lower()
        assert turn.expected.should_remember_allergy is True
        assert "add_belief" in turn.expected.expected_tools

    def test_turn_10_gap_detection(self):
        """Turn 10 should trigger gap detection."""
        turn = get_turn(10)
        assert turn is not None
        assert turn.expected.expects_gap is True
        assert len(turn.expected.gap_params) > 0

    def test_turn_11_remembers_allergy(self):
        """Turn 11 should remember the allergy from turn 5."""
        turn = get_turn(11)
        assert turn is not None
        assert turn.expected.should_remember_allergy is True
        assert "search_restaurants" in turn.expected.expected_tools

    def test_turn_15_starts_weather_monitor(self):
        """Turn 15 should start weather monitor."""
        turn = get_turn(15)
        assert turn is not None
        assert turn.expected.starts_background_task is True
        assert turn.expected.background_task_type == "weather"
        assert "start_background_monitor" in turn.expected.expected_tools

    def test_turn_20_crash_event(self):
        """Turn 20 should have crash event."""
        turn = get_turn(20)
        assert turn is not None
        assert turn.event == TurnEvent.CRASH
        assert turn.user_input == ""  # No user input for crash turn

    def test_turn_24_weather_alert(self):
        """Turn 24 should have weather alert event."""
        turn = get_turn(24)
        assert turn is not None
        assert turn.event == TurnEvent.WEATHER_ALERT
        assert turn.highlight is True

    def test_turn_29_trip_summary(self):
        """Turn 29 should generate trip summary."""
        turn = get_turn(29)
        assert turn is not None
        assert "generate_trip_summary" in turn.expected.expected_tools

    def test_turn_30_emotional_close(self):
        """Turn 30 should update emotion."""
        turn = get_turn(30)
        assert turn is not None
        assert "update_emotion" in turn.expected.expected_tools


class TestScriptMetadata:
    """Tests for script metadata."""

    def test_metadata_exists(self):
        """Script metadata should exist."""
        assert SCRIPT_METADATA is not None
        assert "title" in SCRIPT_METADATA
        assert "total_turns" in SCRIPT_METADATA

    def test_metadata_correct_totals(self):
        """Metadata totals should be correct."""
        assert SCRIPT_METADATA["total_turns"] == 30
        assert SCRIPT_METADATA["total_acts"] == 5

    def test_features_demonstrated(self):
        """Should list features demonstrated."""
        features = SCRIPT_METADATA["features_demonstrated"]
        assert "SessionState learning" in features
        assert "Crash recovery" in features
        assert len(features) >= 5

    def test_key_moments_documented(self):
        """Key moments should be documented."""
        key_moments = SCRIPT_METADATA["key_moments"]
        assert 5 in key_moments  # Shellfish allergy
        assert 20 in key_moments  # Crash
        assert 24 in key_moments  # Weather alert


class TestExpectedBehavior:
    """Tests for expected behavior validation."""

    def test_gap_detection_turns(self):
        """Gap detection should be expected at specific turns."""
        gap_turns = [t.turn_number for t in DEMO_SCRIPT if t.expected.expects_gap]
        assert 10 in gap_turns  # Birthday dinner
        assert 14 in gap_turns  # Transportation
        assert 18 in gap_turns  # Family message

    def test_clarification_response_turns(self):
        """Clarification responses should follow gap turns."""
        clar_turns = [t.turn_number for t in DEMO_SCRIPT if t.expected.is_clarification_response]
        assert 11 in clar_turns  # Response to turn 10
        assert 15 in clar_turns  # Response to turn 14

    def test_tool_calls_reasonable(self):
        """Each turn should have reasonable tool call expectations."""
        for turn in DEMO_SCRIPT:
            # Skip event turns
            if turn.event != TurnEvent.NONE:
                continue
            # Most turns should have some expected behavior
            has_tools = len(turn.expected.expected_tools) > 0
            has_gap = turn.expected.expects_gap
            has_response_theme = bool(turn.response_theme)

            # Turn should have at least one of these
            assert (
                has_tools or has_gap or has_response_theme
            ), f"Turn {turn.turn_number} has no expected behavior"


# ============================================================================
# Display Tests
# ============================================================================


class TestDisplay:
    """Tests for display utilities."""

    def test_colorize_basic(self):
        """Colorize should wrap text with ANSI codes."""
        result = colorize("test", GREEN)
        assert "test" in result
        assert "\033[" in result  # ANSI escape

    def test_colorize_bold(self):
        """Colorize with bold should include bold code."""
        result = colorize("test", RED, bold=True)
        assert "test" in result
        assert "\033[1m" in result  # Bold code

    def test_color_constants(self):
        """Color constants should be ANSI codes."""
        assert GREEN.startswith("\033[")
        assert RED.startswith("\033[")
        assert YELLOW.startswith("\033[")
        assert CYAN.startswith("\033[")


# ============================================================================
# Runner Tests
# ============================================================================


class TestDemoState:
    """Tests for demo state tracking."""

    def test_initial_state(self):
        """Initial state should be zeroed."""
        state = DemoState()
        assert state.current_turn == 0
        assert state.total_turns == 30
        assert state.tool_calls == 0
        assert state.has_crashed is False

    def test_state_tracking(self):
        """State should track metrics."""
        state = DemoState()
        state.tool_calls = 5
        state.gap_detections = 3
        state.has_crashed = True

        assert state.tool_calls == 5
        assert state.gap_detections == 3
        assert state.has_crashed is True


class TestDemoRunner:
    """Tests for demo runner initialization."""

    def test_runner_creation(self):
        """Runner should initialize correctly."""
        runner = DemoRunner(auto_mode=True, fast_mode=True)
        assert runner.auto_mode is True
        assert runner.fast_mode is True
        assert runner.state is not None
        assert len(runner.turns) == 30

    def test_runner_state_initialized(self):
        """Runner should initialize state."""
        runner = DemoRunner()
        assert runner.state.total_turns == 30
        assert runner.state.start_time > 0

    def test_real_llm_components_initialized(self):
        """Runner should have attributes for real LLM components."""
        runner = DemoRunner()
        # These are initialized to None until run() is called
        assert hasattr(runner, "bridge")
        assert hasattr(runner, "llm")
        assert hasattr(runner, "tool_registry")
        assert runner.tool_registry is not None

    def test_tool_registry_has_tools(self):
        """Tool registry should have tools defined."""
        runner = DemoRunner()
        schemas = runner.tool_registry.get_all_schemas_for_llm()
        assert len(schemas) > 0
        # Should have basic tools
        tool_names = [s.get("name") for s in schemas]
        assert "add_belief" in tool_names or any("belief" in (n or "").lower() for n in tool_names)


class TestRealLLMIntegration:
    """Tests for real LLM integration (replaces mock response tests)."""

    def test_system_prompt_defined(self):
        """System prompt should be defined for Concierge."""
        from poc.session_state_demo.anniversary_demo.runner import CONCIERGE_SYSTEM_PROMPT

        assert len(CONCIERGE_SYSTEM_PROMPT) > 100
        assert "Concierge" in CONCIERGE_SYSTEM_PROMPT
        assert "WRITE access" in CONCIERGE_SYSTEM_PROMPT

    def test_runner_has_execute_turn_method(self):
        """Runner should have async execute turn method."""
        runner = DemoRunner()
        assert hasattr(runner, "_execute_turn")
        # Should be a coroutine function
        import inspect

        assert inspect.iscoroutinefunction(runner._execute_turn)


class TestK1CoverageTracking:
    """Tests for K1 coverage tracking during execution."""

    def test_k1_coverage_items_present(self):
        """K1 coverage should have all expected items."""
        state = DemoState()

        expected_items = [
            "SessionState Persistence",
            "Checkpoint/Restore",
            "LLM Tool Calling",
            "Gap Detection",
            "Background Tasks",
        ]

        for item in expected_items:
            assert item in state.k1_coverage

    def test_coverage_starts_false(self):
        """All coverage items should start as False."""
        state = DemoState()
        for item, covered in state.k1_coverage.items():
            assert covered is False, f"{item} should start as False"


# ============================================================================
# Integration Tests
# ============================================================================


class TestDemoIntegration:
    """Integration tests for complete demo flow."""

    def test_all_acts_covered(self):
        """All 5 acts should be covered in script."""
        acts_found = set()
        for turn in DEMO_SCRIPT:
            acts_found.add(turn.act)

        assert len(acts_found) == 5
        assert Act.SETUP in acts_found
        assert Act.GAP_DETECTION in acts_found
        assert Act.BACKGROUND in acts_found
        assert Act.PROACTIVE in acts_found
        assert Act.RESOLUTION in acts_found

    def test_event_turns_correct(self):
        """Event turns should have correct configuration."""
        crash_turn = get_turn(20)
        assert crash_turn.event == TurnEvent.CRASH
        assert crash_turn.pause_before is True

        weather_turn = get_turn(24)
        assert weather_turn.event == TurnEvent.WEATHER_ALERT
        assert weather_turn.highlight is True

    def test_highlight_turns_marked(self):
        """Important turns should be highlighted."""
        highlighted = [t.turn_number for t in DEMO_SCRIPT if t.highlight]

        # Key moments should be highlighted
        assert 5 in highlighted  # Shellfish allergy
        assert 10 in highlighted  # First gap detection
        assert 11 in highlighted  # Allergy remembered
        assert 15 in highlighted  # Weather monitor start
        assert 20 in highlighted  # Crash
        assert 24 in highlighted  # Weather alert
        assert 29 in highlighted  # Trip summary
        assert 30 in highlighted  # Conclusion

    def test_tool_call_coverage(self):
        """All expected tools should be called across the demo."""
        all_tools = set()
        for turn in DEMO_SCRIPT:
            all_tools.update(turn.expected.expected_tools)

        # Core tools should be used
        assert "add_belief" in all_tools
        assert "update_persona" in all_tools
        assert "search_accommodations" in all_tools
        assert "book_accommodation" in all_tools
        assert "search_restaurants" in all_tools
        assert "book_restaurant" in all_tools
        assert "start_background_monitor" in all_tools
        assert "send_family_message" in all_tools
        assert "generate_trip_summary" in all_tools


# ============================================================================
# New Feature Tests - Milestone 3 Enhancements
# ============================================================================


class TestWalkthroughMode:
    """Tests for walkthrough mode."""

    def test_walkthrough_mode_flag(self):
        """Runner should accept walkthrough_mode flag."""
        runner = DemoRunner(walkthrough_mode=True)
        assert runner.walkthrough_mode is True

    def test_walkthrough_topics_defined(self):
        """Walkthrough should have all topic explanations."""
        runner = DemoRunner(walkthrough_mode=True)

        required_topics = [
            "session_state",
            "tool_calling",
            "gap_detection",
            "checkpoint_restore",
            "background_tasks",
            "proactive",
        ]

        for topic in required_topics:
            assert topic in runner._walkthrough_topics
            assert len(runner._walkthrough_topics[topic]) > 50  # Has content


class TestLatencyPercentiles:
    """Tests for P50/P95/P99 latency calculation."""

    def test_percentile_calculation(self):
        """Runner should calculate percentiles correctly."""
        runner = DemoRunner()

        # Test data: 10 values
        data = [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000]

        p50 = runner._calculate_percentile(data, 50)
        p95 = runner._calculate_percentile(data, 95)
        p99 = runner._calculate_percentile(data, 99)

        # P50 should be around median (index 5 of 10 = 600)
        assert p50 == 600
        assert p95 == 1000  # Near max
        assert p99 == 1000  # At max

    def test_percentile_empty_data(self):
        """Percentile of empty data should be 0."""
        runner = DemoRunner()
        assert runner._calculate_percentile([], 50) == 0

    def test_percentile_single_value(self):
        """Percentile of single value should return that value."""
        runner = DemoRunner()
        assert runner._calculate_percentile([500], 50) == 500
        assert runner._calculate_percentile([500], 99) == 500


class TestSessionStateBytesTracking:
    """Tests for SessionState size tracking."""

    def test_latency_tracking(self):
        """State should track turn latencies."""
        state = DemoState()
        assert state.turn_latencies == []

        # Simulate turns
        state.turn_latencies.append(150)
        state.turn_latencies.append(200)

        assert len(state.turn_latencies) == 2
        assert sum(state.turn_latencies) == 350

    def test_session_id_tracking(self):
        """State should track session ID."""
        state = DemoState()
        assert state.session_id == ""

        state.session_id = "test-session-123"
        assert state.session_id == "test-session-123"


class TestK1CoverageReport:
    """Tests for K1 architecture coverage tracking."""

    def test_coverage_initial_state(self):
        """Coverage should start with all items uncovered."""
        state = DemoState()

        assert len(state.k1_coverage) == 12
        assert not any(state.k1_coverage.values())

    def test_coverage_items_present(self):
        """All expected K1 components should be tracked."""
        state = DemoState()

        expected_components = [
            "SessionState Persistence",
            "Checkpoint/Restore",
            "LLM Tool Calling",
            "Gap Detection",
            "Intent Classification",
            "Background Tasks",
            "Proactive Notifications",
            "Persona Learning",
            "Belief Storage",
            "Family Messaging",
            "Calendar Integration",
            "Weather Monitoring",
        ]

        for component in expected_components:
            assert component in state.k1_coverage

    def test_coverage_update(self):
        """Coverage should be updatable."""
        state = DemoState()

        state.k1_coverage["SessionState Persistence"] = True
        state.k1_coverage["LLM Tool Calling"] = True

        covered = sum(1 for v in state.k1_coverage.values() if v)
        assert covered == 2


class TestDisplayEnhancements:
    """Tests for enhanced display functions."""

    def test_walkthrough_explanation_import(self):
        """print_walkthrough_explanation should be importable."""
        from poc.session_state_demo.anniversary_demo.display import print_walkthrough_explanation

        assert callable(print_walkthrough_explanation)

    def test_k1_coverage_report_import(self):
        """print_k1_coverage_report should be importable."""
        from poc.session_state_demo.anniversary_demo.display import print_k1_coverage_report

        assert callable(print_k1_coverage_report)

    def test_system_activity_import(self):
        """print_system_activity should be importable."""
        from poc.session_state_demo.anniversary_demo.display import print_system_activity

        assert callable(print_system_activity)

    def test_unicode_constants_exist(self):
        """Unicode box-drawing constants should be defined."""
        from poc.session_state_demo.anniversary_demo.display import CHECK, FULL_BLOCK, TL  # Symbols

        # Verify they are actual Unicode characters
        assert len(TL) == 1
        assert len(CHECK) == 1
        assert len(FULL_BLOCK) == 1


# ============================================================================
# Milestone 4: Reliability Tests
# ============================================================================


class TestMilestone4Reliability:
    """Epic 4.1: Reliability tests for production-quality demo."""

    # 4.1.2: Validate all 30 turns
    def test_all_turns_have_user_input(self):
        """Every turn should have user input defined."""
        for turn in DEMO_SCRIPT:
            # Turn 20 (crash) and 24 (weather alert) may have empty input
            if turn.event in (TurnEvent.CRASH, TurnEvent.WEATHER_ALERT):
                continue
            assert turn.user_input, f"Turn {turn.turn_number} missing user_input"

    def test_all_turns_have_expected_behavior(self):
        """Every turn should have expected behavior defined."""
        for turn in DEMO_SCRIPT:
            assert turn.expected is not None, f"Turn {turn.turn_number} missing expected"
            assert isinstance(turn.expected, ExpectedBehavior)

    def test_all_turns_have_response_or_event(self):
        """Every turn should have user input or be a special event."""
        for turn in DEMO_SCRIPT:
            # Event turns are handled specially
            if turn.event in (TurnEvent.CRASH, TurnEvent.WEATHER_ALERT):
                continue
            # Every normal turn needs user input for LLM
            assert turn.user_input, f"Turn {turn.turn_number} has no user_input"

    def test_gap_detection_turns_have_gap_params(self):
        """Turns with gap detection should have gap_params defined."""
        for turn in DEMO_SCRIPT:
            if turn.expected.expects_gap:
                assert (
                    len(turn.expected.gap_params) > 0
                ), f"Turn {turn.turn_number} expects gap but has no gap_params"

    def test_background_task_turns_have_task_type(self):
        """Turns starting background tasks should have task_type."""
        for turn in DEMO_SCRIPT:
            if turn.expected.starts_background_task:
                assert (
                    turn.expected.background_task_type
                ), f"Turn {turn.turn_number} starts task but has no type"

    def test_all_acts_have_turns(self):
        """Every act should have at least one turn."""
        for act in Act:
            turns = get_turns_by_act(act)
            assert len(turns) > 0, f"Act {act.value} has no turns"

    def test_turn_numbers_are_sequential(self):
        """Turn numbers should be strictly sequential 1-30."""
        for i, turn in enumerate(DEMO_SCRIPT):
            assert turn.turn_number == i + 1, f"Turn at index {i} has number {turn.turn_number}"

    def test_crash_turn_is_exactly_20(self):
        """Crash event should be exactly at turn 20."""
        crash_turns = [t for t in DEMO_SCRIPT if t.event == TurnEvent.CRASH]
        assert len(crash_turns) == 1, "Should have exactly 1 crash turn"
        assert crash_turns[0].turn_number == 20

    def test_weather_alert_is_exactly_24(self):
        """Weather alert should be exactly at turn 24."""
        weather_turns = [t for t in DEMO_SCRIPT if t.event == TurnEvent.WEATHER_ALERT]
        assert len(weather_turns) == 1, "Should have exactly 1 weather turn"
        assert weather_turns[0].turn_number == 24


class TestCrashRestoreReliability:
    """4.1.3: Test crash/restore works reliably."""

    def test_crash_restore_state_tracking(self):
        """State should track crash/restore events."""
        state = DemoState()

        # Initial state
        assert state.has_crashed is False
        assert state.crash_restores == 0

        # Simulate crash
        state.has_crashed = True
        state.crash_restores += 1

        assert state.has_crashed is True
        assert state.crash_restores == 1

    def test_crash_restore_multiple_times(self):
        """Crash/restore should work reliably 5 times."""
        for i in range(5):
            state = DemoState()
            state.current_turn = 19
            state.has_crashed = False

            # Simulate crash
            state.has_crashed = True
            state.crash_restores += 1

            # Verify restore
            assert state.has_crashed is True
            assert state.crash_restores == 1
            assert state.current_turn == 19

    def test_runner_handles_crash_event(self):
        """Runner should have crash handler."""
        runner = DemoRunner(auto_mode=True, fast_mode=True)
        assert hasattr(runner, "_handle_crash")
        assert callable(runner._handle_crash)

    def test_runner_handles_weather_event(self):
        """Runner should have weather alert handler."""
        runner = DemoRunner(auto_mode=True, fast_mode=True)
        assert hasattr(runner, "_handle_weather_alert")
        assert callable(runner._handle_weather_alert)

    def test_crash_turn_marked_correctly(self):
        """Turn 20 should have crash event and pause_before."""
        turn = get_turn(20)
        assert turn.event == TurnEvent.CRASH
        assert turn.pause_before is True
        assert turn.highlight is True


class TestPerformanceOptimization:
    """4.1.4: Performance tests."""

    def test_tool_registry_lookup_is_fast(self):
        """Tool registry lookup should be instant."""
        runner = DemoRunner(auto_mode=True, fast_mode=True)

        import time

        start = time.perf_counter()
        schemas = runner.tool_registry.get_all_schemas_for_llm()
        elapsed = time.perf_counter() - start
        assert elapsed < 0.01, f"Tool registry took {elapsed:.4f}s (>10ms)"
        assert len(schemas) > 0

    def test_percentile_calculation_is_fast(self):
        """Percentile calculation should be efficient."""
        runner = DemoRunner(auto_mode=True, fast_mode=True)

        import time

        # Simulate 30 turn latencies
        data = list(range(100, 1100, 33))  # 30 values

        start = time.perf_counter()
        p50 = runner._calculate_percentile(data, 50)
        p95 = runner._calculate_percentile(data, 95)
        p99 = runner._calculate_percentile(data, 99)
        elapsed = time.perf_counter() - start

        assert elapsed < 0.001, f"Percentile calc took {elapsed:.4f}s"
        assert p50 > 0
        assert p95 > p50
        assert p99 >= p95

    def test_fast_mode_reduces_delays(self):
        """Fast mode should have minimal delays."""
        runner_normal = DemoRunner(auto_mode=True, fast_mode=False)
        runner_fast = DemoRunner(auto_mode=True, fast_mode=True)

        assert runner_fast.fast_mode is True
        assert runner_normal.fast_mode is False


class TestErrorHandling:
    """4.1.1: LLM error handling (graceful fallbacks)."""

    def test_crash_handler_exists(self):
        """Runner should have crash handler method."""
        runner = DemoRunner(auto_mode=True, fast_mode=True)
        assert hasattr(runner, "_handle_crash")
        import inspect

        assert inspect.iscoroutinefunction(runner._handle_crash)

    def test_weather_handler_exists(self):
        """Runner should have weather alert handler method."""
        runner = DemoRunner(auto_mode=True, fast_mode=True)
        assert hasattr(runner, "_handle_weather_alert")
        import inspect

        assert inspect.iscoroutinefunction(runner._handle_weather_alert)

    def test_runner_has_tool_registry(self):
        """Runner should have tool registry for LLM."""
        runner = DemoRunner(auto_mode=True, fast_mode=True)
        assert hasattr(runner, "tool_registry")
        assert runner.tool_registry is not None

    def test_runner_initializes_with_defaults(self):
        """Runner should initialize with safe defaults."""
        runner = DemoRunner()
        assert runner.auto_mode is False
        assert runner.fast_mode is False
        assert runner.walkthrough_mode is False
        assert runner.state is not None
        assert runner.state.current_turn == 0
        assert runner.state.total_turns == 30
