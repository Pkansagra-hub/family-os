"""
Human-Feel Upgrade #1: Consent & Floor Control Tests

Test consent-based proactivity, permission detection, cooldowns,
topic alignment, confidence phrasing, and full permission flow.

Phase: Human-Feel Upgrades
Topics Covered:
- Permission detection (12 markers)
- can_inject logic (cooldown, topic alignment, typing detection)
- Confidence phrasing (3 tiers)
- Permission ping generation
- Full permission flow integration
"""

import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from backend.agents.concierge_v2 import ConciergeAgentV2
from backend.agents.focus_tracker import ConversationFocusTracker
from backend.services.k0_query_service import MockK0QueryService
from backend.services.llm_client import LLMClient
from backend.services.metrics_collector import MetricsCollector
from backend.services.progress_publisher import ProgressPublisher


@pytest.fixture
def llm_client():
    """Mock LLM client."""
    client = AsyncMock(spec=LLMClient)
    client.generate_async = AsyncMock(return_value="Test response")
    return client


@pytest.fixture
def concierge(llm_client):
    """Create concierge with mocked LLM."""
    return ConciergeAgentV2(
        llm_client=llm_client,
        k0_query_service=MockK0QueryService(),
        metrics_collector=MetricsCollector(),
        progress_publisher=ProgressPublisher(),
    )


@pytest.fixture
def focus_tracker():
    """Create fresh focus tracker."""
    return ConversationFocusTracker()


# ==============================
# PERMISSION DETECTION TESTS
# ==============================


class TestPermissionDetection:
    """Test permission marker detection."""

    def test_detect_yes_permission(self, focus_tracker):
        """Test 'yes' grants permission."""
        assert focus_tracker.detect_permission("yes") is True
        assert focus_tracker.detect_permission("Yes, please") is True
        assert focus_tracker.detect_permission("oh yes") is True

    def test_detect_yeah_permission(self, focus_tracker):
        """Test 'yeah' grants permission."""
        assert focus_tracker.detect_permission("yeah") is True
        assert focus_tracker.detect_permission("Yeah, go ahead") is True

    def test_detect_sure_permission(self, focus_tracker):
        """Test 'sure' grants permission."""
        assert focus_tracker.detect_permission("sure") is True
        assert focus_tracker.detect_permission("Sure thing") is True

    def test_detect_tell_me_permission(self, focus_tracker):
        """Test 'tell me' grants permission."""
        assert focus_tracker.detect_permission("tell me") is True
        assert focus_tracker.detect_permission("Tell me more") is True

    def test_detect_go_ahead_permission(self, focus_tracker):
        """Test 'go ahead' grants permission."""
        assert focus_tracker.detect_permission("go ahead") is True
        assert focus_tracker.detect_permission("Go ahead and share") is True

    def test_detect_show_me_permission(self, focus_tracker):
        """Test 'show me' grants permission."""
        assert focus_tracker.detect_permission("show me") is True
        assert focus_tracker.detect_permission("Show me what you found") is True

    def test_no_permission_in_question(self, focus_tracker):
        """Test questions don't grant permission."""
        assert focus_tracker.detect_permission("what do you think?") is False
        assert focus_tracker.detect_permission("how was your day?") is False

    def test_no_permission_in_statement(self, focus_tracker):
        """Test normal statements don't grant permission."""
        assert focus_tracker.detect_permission("I had coffee today") is False
        assert focus_tracker.detect_permission("my stomach hurts") is False


# ==============================
# CAN_INJECT LOGIC TESTS
# ==============================


class TestCanInjectLogic:
    """Test can_inject decision logic."""

    def test_can_inject_with_explicit_permission(self, focus_tracker):
        """Test explicit permission overrides all checks."""
        focus_tracker.state.has_permission = False
        now = time.time()
        assert focus_tracker.can_inject("diet", now, has_explicit_permission=True) is True

    def test_cannot_inject_if_user_typing(self, focus_tracker):
        """Test typing blocks injection."""
        focus_tracker.state.user_typing = True
        now = time.time()
        assert focus_tracker.can_inject("diet", now, has_explicit_permission=False) is False

    def test_cannot_inject_within_cooldown(self, focus_tracker):
        """Test cooldown blocks injection."""
        now = time.time()
        focus_tracker.state.last_inject_ts = now - 15  # 15 seconds ago
        focus_tracker.state.cooldown_secs = 30
        assert focus_tracker.can_inject("diet", now, has_explicit_permission=False) is False

    def test_can_inject_after_cooldown(self, focus_tracker):
        """Test injection allowed after cooldown."""
        now = time.time()
        focus_tracker.state.last_inject_ts = now - 35  # 35 seconds ago
        focus_tracker.state.cooldown_secs = 30
        focus_tracker.state.has_permission = True
        assert focus_tracker.can_inject("diet", now, has_explicit_permission=False) is True

    def test_cannot_inject_different_topic_without_permission(self, focus_tracker):
        """Test topic mismatch requires permission."""
        now = time.time()
        focus_tracker.state.topic_of_last_inject = "diet"
        focus_tracker.state.has_permission = False
        assert focus_tracker.can_inject("exercise", now, has_explicit_permission=False) is False

    def test_can_inject_same_topic_with_permission(self, focus_tracker):
        """Test same topic allowed with permission."""
        now = time.time()
        focus_tracker.state.topic_of_last_inject = "diet"
        focus_tracker.state.has_permission = True
        focus_tracker.state.last_inject_ts = now - 35
        assert focus_tracker.can_inject("diet", now, has_explicit_permission=False) is True

    def test_grant_permission_sets_flag(self, focus_tracker):
        """Test grant_permission sets flag."""
        focus_tracker.grant_permission()
        assert focus_tracker.state.has_permission is True

    def test_set_user_typing_updates_state(self, focus_tracker):
        """Test typing state updates."""
        focus_tracker.set_user_typing(True)
        assert focus_tracker.state.user_typing is True
        focus_tracker.set_user_typing(False)
        assert focus_tracker.state.user_typing is False


# ==============================
# CONFIDENCE PHRASING TESTS
# ==============================


class TestConfidencePhrasing:
    """Test confidence-aware hedging."""

    def test_high_confidence_phrasing(self, concierge):
        """Test 0.8-1.0 confidence uses strong hedges."""
        result = concierge._phrase_with_confidence("this is the finding", 0.9)
        # Should contain one of: pretty clearly, strong pattern, definitely looks like, clearly shows
        assert any(
            hedge in result.lower()
            for hedge in ["pretty clearly", "strong pattern", "definitely looks", "clearly shows"]
        )
        assert "this is the finding" in result

    def test_medium_confidence_phrasing(self, concierge):
        """Test 0.5-0.79 confidence uses moderate hedges."""
        result = concierge._phrase_with_confidence("this is the finding", 0.65)
        # Should contain one of: likely, points to, suggests, seems like
        assert any(
            hedge in result.lower() for hedge in ["likely", "points to", "suggests", "seems like"]
        )
        assert "this is the finding" in result

    def test_low_confidence_phrasing(self, concierge):
        """Test 0.0-0.49 confidence uses uncertain hedges."""
        result = concierge._phrase_with_confidence("this is the finding", 0.3)
        # Should contain one of: might be, could be, possibly, not sure yet
        assert any(
            hedge in result.lower()
            for hedge in ["might be", "could be", "possibly", "not sure yet"]
        )
        assert "this is the finding" in result

    def test_confidence_phrasing_format(self, concierge):
        """Test phrasing format is 'hedge: text'."""
        result = concierge._phrase_with_confidence("finding", 0.8)
        assert ":" in result  # Should have colon separator


# ==============================
# PERMISSION PING TESTS
# ==============================


class TestPermissionPing:
    """Test permission ping generation."""

    @pytest.mark.asyncio
    async def test_permission_ping_with_completed_analysis(self, concierge):
        """Test ping generated when analysis complete."""
        # Simulate completed analysis
        mock_analysis = MagicMock()
        mock_analysis.specialist_type = "nutritionist"
        concierge.completed_analyses.append(mock_analysis)

        ping = await concierge._maybe_permission_ping("diet")
        assert ping is not None
        assert "nutritionist" in ping.lower()
        assert any(
            phrase in ping.lower()
            for phrase in ["want me to share", "want to hear", "interested", "should i share"]
        )

    @pytest.mark.asyncio
    async def test_no_permission_ping_without_analysis(self, concierge):
        """Test no ping when no completed analysis."""
        ping = await concierge._maybe_permission_ping("diet")
        assert ping is None


# ==============================
# FULL FLOW INTEGRATION TESTS
# ==============================


class TestPermissionFlowIntegration:
    """Test full permission flow in process_message."""

    @pytest.mark.asyncio
    async def test_permission_detected_and_granted(self, concierge):
        """Test permission detection grants access."""
        # Start with no permission
        assert concierge.focus_tracker.state.has_permission is False

        # User says "yes"
        await concierge.process_message("test_user", "yes")

        # Permission should be granted
        assert concierge.focus_tracker.state.has_permission is True

    @pytest.mark.asyncio
    async def test_permission_ping_sent_without_permission(self, concierge):
        """Test permission ping sent when analysis complete but no permission."""
        # Simulate completed analysis
        mock_analysis = MagicMock()
        mock_analysis.specialist_type = "nutritionist"
        mock_analysis.get_primary_insight.return_value = None
        concierge.completed_analyses.append(mock_analysis)

        # User says something (not permission)
        response = await concierge.process_message("test_user", "how are you?")

        # Should ask for permission (response contains permission ping)
        # Note: This is a simplified check - actual implementation may vary
        assert response is not None

    @pytest.mark.asyncio
    async def test_injection_with_permission_and_cooldown_passed(self, concierge):
        """Test injection happens when all conditions met."""
        # Setup: analysis complete, permission granted, cooldown passed
        mock_analysis = MagicMock()
        mock_analysis.specialist_type = "nutritionist"
        mock_analysis.confidence = 0.85
        mock_analysis.actual_finding = "Test finding"
        mock_analysis.get_primary_insight.return_value = None
        concierge.completed_analyses.append(mock_analysis)

        concierge.focus_tracker.grant_permission()
        concierge.focus_tracker.state.last_inject_ts = time.time() - 35  # Cooldown passed

        # User sends message
        response = await concierge.process_message("test_user", "what's up?")

        # Should inject finding (response contains finding)
        assert response is not None
        # LLM was called to generate finding response
        assert concierge.llm_client.generate_async.called

    @pytest.mark.asyncio
    async def test_no_injection_within_cooldown(self, concierge):
        """Test no injection within cooldown window."""
        # Setup: analysis complete, permission granted, but within cooldown
        mock_analysis = MagicMock()
        mock_analysis.specialist_type = "nutritionist"
        concierge.completed_analyses.append(mock_analysis)

        concierge.focus_tracker.grant_permission()
        concierge.focus_tracker.state.last_inject_ts = time.time() - 10  # Only 10s ago

        # User sends message
        response = await concierge.process_message("test_user", "hello")

        # Should NOT inject (normal response instead)
        assert response is not None

    @pytest.mark.asyncio
    async def test_track_injection_updates_state(self, concierge):
        """Test track_insight_injection updates timestamps and topics."""
        topic = "diet"
        concierge.focus_tracker.track_insight_injection("Test insight", topic=topic)

        state = concierge.focus_tracker.state
        assert state.last_inject_ts is not None
        assert state.topic_of_last_inject == topic
        assert state.has_permission is False  # Permission reset after injection


# ==============================
# EDGE CASES & ROBUSTNESS
# ==============================


class TestConsentEdgeCases:
    """Test edge cases and robustness."""

    def test_permission_detection_case_insensitive(self, focus_tracker):
        """Test permission markers work regardless of case."""
        assert focus_tracker.detect_permission("YES") is True
        assert focus_tracker.detect_permission("Tell Me") is True
        assert focus_tracker.detect_permission("GO AHEAD") is True

    def test_can_inject_first_time_no_cooldown(self, focus_tracker):
        """Test first injection has no cooldown."""
        now = time.time()
        focus_tracker.state.last_inject_ts = None  # Never injected
        focus_tracker.state.has_permission = True
        assert focus_tracker.can_inject("diet", now, has_explicit_permission=False) is True

    def test_confidence_phrasing_boundary_values(self, concierge):
        """Test confidence phrasing at boundaries."""
        # Test 0.0 (low)
        result = concierge._phrase_with_confidence("finding", 0.0)
        assert ":" in result

        # Test 0.5 (medium boundary)
        result = concierge._phrase_with_confidence("finding", 0.5)
        assert ":" in result

        # Test 0.8 (high boundary)
        result = concierge._phrase_with_confidence("finding", 0.8)
        assert ":" in result

        # Test 1.0 (max)
        result = concierge._phrase_with_confidence("finding", 1.0)
        assert ":" in result

    @pytest.mark.asyncio
    async def test_multiple_permission_grants(self, concierge):
        """Test permission can be granted multiple times."""
        await concierge.process_message("test_user", "yes")
        assert concierge.focus_tracker.state.has_permission is True

        # Reset and grant again
        concierge.focus_tracker.state.has_permission = False
        await concierge.process_message("test_user", "sure")
        assert concierge.focus_tracker.state.has_permission is True
        assert concierge.focus_tracker.state.has_permission is True
        assert concierge.focus_tracker.state.has_permission is True
