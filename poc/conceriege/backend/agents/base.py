"""
BaseAgent - Abstract Base Class for All Specialist Agents

Provides common infrastructure for all specialist agents (nutritionist, psychiatrist, etc.)
including progress tracking, task ID generation, and common interfaces.

Research basis:
- Actor Model (Hewitt 1973) - Agents as actors with capabilities
- Progressive Disclosure (Norman 1988) - Progress updates for user awareness
- SEDA - Staged Event-Driven Architecture (Welsh 2001) - Asynchronous processing

Performance targets:
- Progress emission: <5ms per event
- Task ID generation: <1ms
- Background work: 500-1000ms typical duration
"""

import asyncio
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional

from backend.models.analysis_result import AnalysisResult
from backend.models.conversation_state import ConversationState
from backend.models.progress_event import ProgressEvent
from backend.services.k0_query_service import K0QueryService
from backend.services.metrics_collector import MetricsCollector
from backend.services.progress_publisher import ProgressPublisher


def generate_ulid() -> str:
    """
    Generate ULID (Universally Unique Lexicographically Sortable Identifier).

    For PoC, using timestamp + random suffix for simplicity.
    Production would use proper ULID library.

    Returns:
        ULID string (e.g., "01ARZ3NDEKTSV4RRFFQ69G5FAV")
    """
    import random
    import string

    # Timestamp component (milliseconds since epoch)
    timestamp = int(time.time() * 1000)

    # Random component (10 characters)
    random_suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=10))

    return f"{timestamp}_{random_suffix}"


class BaseAgent(ABC):
    """
    Abstract base class for all specialist agents.

    All specialist agents (nutritionist, psychiatrist, finance_analyst, etc.)
    inherit from this class to get common capabilities:
    - Progress event emission
    - Task ID generation
    - Capability declaration
    - Metrics tracking

    Subclasses must implement:
    - analyze(): Main analysis method
    - get_progress_milestones(): Return milestone definitions

    Example subclass:
        class NutritionistAgent(BaseAgent):
            def analyze(self, query, user_id, context):
                # Implementation
                pass

            def get_progress_milestones(self):
                return [
                    {"milestone": 1, "percent": 20, "message": "📊 Checking diet..."},
                    # ... 5 milestones total
                ]
    """

    # Default milestones (subclasses override with specific messages)
    DEFAULT_MILESTONES = [
        {"milestone": 1, "percent": 20, "message": "📊 Starting analysis..."},
        {"milestone": 2, "percent": 40, "message": "🔍 Processing data..."},
        {"milestone": 3, "percent": 60, "message": "🧠 Finding patterns..."},
        {"milestone": 4, "percent": 80, "message": "💡 Generating insights..."},
        {"milestone": 5, "percent": 100, "message": "✅ Complete"},
    ]

    def __init__(
        self,
        agent_id: str,
        agent_type: str,
        k0_query_service: K0QueryService,
        metrics_collector: MetricsCollector,
        progress_publisher: Optional[ProgressPublisher] = None,
    ):
        """
        Initialize base agent.

        Args:
            agent_id: Unique agent identifier (e.g., "nut_001")
            agent_type: Agent type (e.g., "nutritionist", "psychiatrist")
            k0_query_service: K0 data access service
            metrics_collector: Performance metrics tracker
            progress_publisher: Optional progress publisher for streaming events
        """
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.k0_query_service = k0_query_service
        self.metrics_collector = metrics_collector
        self.progress_publisher = progress_publisher
        self._progress_callbacks: List = []

    @abstractmethod
    async def analyze(self, query: str, user_id: str, context: ConversationState) -> AnalysisResult:
        """
        Main analysis method (must be implemented by subclasses).

        Args:
            query: User's query/concern
            user_id: FamilyOS user ID
            context: Conversation state for context

        Returns:
            AnalysisResult with insights and evidence

        Example implementation:
            async def analyze(self, query, user_id, context):
                task_id = self._create_task_id()

                # Milestone 1
                await self.emit_progress(task_id, 1, 20, "Starting...")

                # Do work...
                data = await self.k0_query_service.query(...)

                # Milestone 2
                await self.emit_progress(task_id, 2, 40, "Analyzing...")

                # ... continue

                return AnalysisResult(...)
        """
        pass

    @abstractmethod
    def get_progress_milestones(self) -> List[dict]:
        """
        Get progress milestone definitions (must be implemented by subclasses).

        Returns:
            List of 5 milestone dictionaries with milestone, percent, message

        Example:
            [
                {"milestone": 1, "percent": 20, "message": "📊 Checking diet..."},
                {"milestone": 2, "percent": 40, "message": "🧠 Analyzing patterns..."},
                {"milestone": 3, "percent": 60, "message": "🔗 Finding correlations..."},
                {"milestone": 4, "percent": 80, "message": "💡 Generating insights..."},
                {"milestone": 5, "percent": 100, "message": "✅ Complete"},
            ]
        """
        pass

    async def emit_progress(self, task_id: str, milestone: int, percent: int, message: str) -> None:
        """
        Emit progress event (concrete implementation).

        Creates ProgressEvent and calls registered callbacks.
        Also publishes to ProgressPublisher if available for streaming to CLI.

        Args:
            task_id: Task identifier
            milestone: Milestone number (1-5)
            percent: Progress percentage (0-100)
            message: Human-readable message

        Example:
            await self.emit_progress(
                "task_123",
                2,
                40,
                "🧠 Analyzing patterns..."
            )
        """
        event = ProgressEvent(
            task_id=task_id,
            milestone=milestone,
            percent=percent,
            message=message,
            timestamp=datetime.utcnow(),
        )

        # Publish to ProgressPublisher for CLI streaming
        if self.progress_publisher:
            self.progress_publisher.publish(task_id, event)

        # Call registered callbacks (backward compatibility)
        for callback in self._progress_callbacks:
            if asyncio.iscoroutinefunction(callback):
                await callback(event)
            else:
                callback(event)

    def register_progress_callback(self, callback):
        """
        Register callback for progress events.

        Args:
            callback: Function to call with ProgressEvent
        """
        self._progress_callbacks.append(callback)

    def _create_task_id(self) -> str:
        """
        Generate unique task ID (concrete implementation).

        Uses ULID (Universally Unique Lexicographically Sortable Identifier)
        for unique, sortable IDs.

        Returns:
            Task ID string (e.g., "1699444800000_ABC123DEF4")

        Example:
            task_id = self._create_task_id()
            # "1699444800000_ABC123DEF4"
        """
        return generate_ulid()

    def get_capabilities(self) -> List[str]:
        """
        Get agent capabilities (concrete implementation).

        Returns list of capabilities this agent provides.
        Subclasses can override to add specific capabilities.

        Returns:
            List of capability strings

        Example:
            ["analyze_diet", "correlate_gerd", "detect_triggers"]
        """
        return ["analyze", "progress_tracking", "async_execution"]
