"""
ConfidenceScorer - 4-Factor Agent Confidence Calculation

Used by agents to compute bidding confidence when receiving TaskAnnouncements.
Agents only bid if confidence ≥ 0.5 (50% threshold).

4 Factors (weighted):
1. Capability Match (40%): Do I have required tools?
2. Success Rate (30%): Historical performance for this task type
3. Load (20% inverse): Current mailbox depth (lower = better)
4. Context Availability (10%): Do I have session context cached?

Formula:
confidence = capability_match_score + success_rate_score + load_score + context_score
Range: 0.0 - 1.0

References:
- Epic 6.1.2 - Agent Confidence Scoring
- docs/whiteboard/chat_experience.md - Phase 1 confidence scoring (4 factors)
- ADR-0006a - Contract Net Protocol Phase 1
"""

from typing import Any, Dict, List, Optional, Set

import structlog

logger = structlog.get_logger(__name__)


class ConfidenceScorer:
    """
    Utility class for computing agent confidence scores.

    Used by agents when evaluating TaskAnnouncements to determine
    whether to submit a proposal (bid).
    """

    # Confidence weights for 4 factors
    WEIGHT_CAPABILITY = 0.4  # 40% - most important
    WEIGHT_SUCCESS_RATE = 0.3  # 30%
    WEIGHT_LOAD = 0.2  # 20% (inverse - lower load is better)
    WEIGHT_CONTEXT = 0.1  # 10%

    # Bidding threshold
    MIN_CONFIDENCE_TO_BID = 0.5  # 50% minimum confidence

    # Default success rate for agents without history
    DEFAULT_SUCCESS_RATE = 0.7  # Assume 70% success for new agents

    @staticmethod
    def compute_confidence(
        agent_tools: Set[str],
        required_tools: List[str],
        success_rate: Optional[float] = None,
        mailbox_depth: int = 0,
        mailbox_capacity: int = 50,
        has_session_context: bool = False,
    ) -> Dict[str, Any]:
        """
        Compute agent confidence score for a task.

        Args:
            agent_tools: Set of tools the agent has access to
            required_tools: List of tools required by the task
            success_rate: Historical success rate (0.0-1.0), None = use default
            mailbox_depth: Current mailbox queue depth
            mailbox_capacity: Maximum mailbox capacity
            has_session_context: Whether agent has session context cached

        Returns:
            Dict with:
                - confidence: float (0.0-1.0) total confidence score
                - should_bid: bool (True if confidence ≥ threshold)
                - factors: dict with individual factor scores for explainability
        """
        # Factor 1: Capability Match (40%)
        capability_score = ConfidenceScorer._compute_capability_match(agent_tools, required_tools)

        # Factor 2: Success Rate (30%)
        success_rate_score = ConfidenceScorer._compute_success_rate(success_rate)

        # Factor 3: Load (20%, inverse)
        load_score = ConfidenceScorer._compute_load_score(mailbox_depth, mailbox_capacity)

        # Factor 4: Context Availability (10%)
        context_score = ConfidenceScorer._compute_context_score(has_session_context)

        # Total confidence (weighted sum)
        confidence = capability_score + success_rate_score + load_score + context_score

        # Decision: bid if confidence ≥ threshold
        # HARD REQUIREMENT: Must have 100% capability match (all required tools)
        # Even if other factors are high, agents cannot bid without all tools
        has_all_tools = capability_score == ConfidenceScorer.WEIGHT_CAPABILITY
        should_bid = has_all_tools and (confidence >= ConfidenceScorer.MIN_CONFIDENCE_TO_BID)

        return {
            "confidence": round(confidence, 3),
            "should_bid": should_bid,
            "threshold": ConfidenceScorer.MIN_CONFIDENCE_TO_BID,
            "factors": {
                "capability_match": round(capability_score, 3),
                "success_rate": round(success_rate_score, 3),
                "load": round(load_score, 3),
                "context_availability": round(context_score, 3),
            },
        }

    @staticmethod
    def _compute_capability_match(agent_tools: Set[str], required_tools: List[str]) -> float:
        """
        Compute capability match score (40% weight).

        Formula: (matching_tools / required_tools) × 0.4

        Args:
            agent_tools: Tools the agent has
            required_tools: Tools required by task

        Returns:
            Score: 0.0-0.4
        """
        if not required_tools:
            # No tools required - perfect match
            return ConfidenceScorer.WEIGHT_CAPABILITY

        matching_tools = len([tool for tool in required_tools if tool in agent_tools])
        match_ratio = matching_tools / len(required_tools)

        score = match_ratio * ConfidenceScorer.WEIGHT_CAPABILITY

        logger.debug(
            "capability_match_computed",
            matching_tools=matching_tools,
            required_tools=len(required_tools),
            match_ratio=match_ratio,
            score=score,
        )

        return score

    @staticmethod
    def _compute_success_rate(success_rate: Optional[float]) -> float:
        """
        Compute success rate score (30% weight).

        Formula: success_rate × 0.3

        Args:
            success_rate: Historical success rate (0.0-1.0) or None

        Returns:
            Score: 0.0-0.3
        """
        if success_rate is None:
            # No history - use default assumption
            success_rate = ConfidenceScorer.DEFAULT_SUCCESS_RATE

        # Clamp to 0.0-1.0 range
        success_rate = max(0.0, min(1.0, success_rate))

        score = success_rate * ConfidenceScorer.WEIGHT_SUCCESS_RATE

        logger.debug(
            "success_rate_computed",
            success_rate=success_rate,
            score=score,
        )

        return score

    @staticmethod
    def _compute_load_score(mailbox_depth: int, mailbox_capacity: int) -> float:
        """
        Compute load score (20% weight, inverse).

        Lower load = higher score (better).

        Formula: (1 - mailbox_depth / capacity) × 0.2

        Args:
            mailbox_depth: Current queue depth
            mailbox_capacity: Maximum capacity

        Returns:
            Score: 0.0-0.2
        """
        if mailbox_capacity <= 0:
            # Invalid capacity - assume full load
            return 0.0

        # Clamp depth to capacity
        mailbox_depth = min(mailbox_depth, mailbox_capacity)

        load_ratio = mailbox_depth / mailbox_capacity
        availability = 1.0 - load_ratio

        score = availability * ConfidenceScorer.WEIGHT_LOAD

        logger.debug(
            "load_score_computed",
            mailbox_depth=mailbox_depth,
            mailbox_capacity=mailbox_capacity,
            load_ratio=load_ratio,
            availability=availability,
            score=score,
        )

        return score

    @staticmethod
    def _compute_context_score(has_session_context: bool) -> float:
        """
        Compute context availability score (10% weight).

        Formula: 0.1 if context available, else 0.0

        Args:
            has_session_context: Whether agent has session context cached

        Returns:
            Score: 0.0 or 0.1
        """
        score = ConfidenceScorer.WEIGHT_CONTEXT if has_session_context else 0.0

        logger.debug(
            "context_score_computed",
            has_session_context=has_session_context,
            score=score,
        )

        return score

    @staticmethod
    def validate_confidence_components(
        agent_tools: Set[str],
        required_tools: List[str],
        success_rate: Optional[float],
        mailbox_depth: int,
        mailbox_capacity: int,
    ) -> tuple[bool, Optional[str]]:
        """
        Validate confidence calculation inputs.

        Returns:
            (is_valid, error_message)
        """
        # Validate tools
        if not isinstance(agent_tools, set):
            return False, "agent_tools must be a set"
        if not isinstance(required_tools, list):
            return False, "required_tools must be a list"

        # Validate success rate
        if success_rate is not None:
            if not isinstance(success_rate, (int, float)):
                return False, "success_rate must be a number"
            if not 0.0 <= success_rate <= 1.0:
                return False, "success_rate must be between 0.0 and 1.0"

        # Validate mailbox metrics
        if not isinstance(mailbox_depth, int) or mailbox_depth < 0:
            return False, "mailbox_depth must be a non-negative integer"
        if not isinstance(mailbox_capacity, int) or mailbox_capacity <= 0:
            return False, "mailbox_capacity must be a positive integer"
        if mailbox_depth > mailbox_capacity:
            return False, "mailbox_depth cannot exceed mailbox_capacity"

        return True, None
