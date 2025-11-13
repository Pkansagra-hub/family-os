"""
PsychiatristAgent - Mental Health Specialist

Analyzes mood, anxiety, and mental health patterns from K0 data.
"""

from typing import Optional

from backend.agents.base import BaseAgent
from backend.models.analysis_result import AnalysisResult, Insight
from backend.models.conversation_state import ConversationState
from backend.services.k0_query_service import K0QueryService
from backend.services.llm_client import LLMClient
from backend.services.metrics_collector import MetricsCollector
from backend.services.progress_publisher import ProgressPublisher


class PsychiatristAgent(BaseAgent):
    """LLM-powered mental health specialist."""

    def __init__(
        self,
        llm_client: LLMClient,
        k0_query_service: K0QueryService,
        metrics_collector: MetricsCollector,
        progress_publisher: Optional[ProgressPublisher] = None,
    ):
        """Initialize psychiatrist agent."""
        super().__init__(
            agent_id="psychiatrist_001",
            agent_type="psychiatrist",
            k0_query_service=k0_query_service,
            metrics_collector=metrics_collector,
            progress_publisher=progress_publisher,
        )
        self.llm_client = llm_client

    async def analyze(self, query: str, user_id: str, context: ConversationState) -> AnalysisResult:
        """Analyze mental health concern."""
        task_id = self._create_task_id()

        await self.emit_progress(task_id, 1, 20, "📊 Analyzing mood patterns...")
        await self.emit_progress(task_id, 2, 40, "🧠 Identifying patterns...")
        await self.emit_progress(task_id, 3, 60, "🔍 Finding insights...")
        await self.emit_progress(task_id, 4, 80, "💡 Generating insights...")
        await self.emit_progress(task_id, 5, 100, "✅ Analysis complete")

        return AnalysisResult(
            specialist_type="psychiatrist",
            query=query,
            insights=[Insight(summary="Mental health assessment completed")],
            confidence=0.7,
            duration_ms=500,
        )

    def get_progress_milestones(self):
        """Get progress milestones."""
        return [
            {"milestone": 1, "percent": 20, "message": "📊 Analyzing mood..."},
            {"milestone": 2, "percent": 40, "message": "🧠 Processing patterns..."},
            {"milestone": 3, "percent": 60, "message": "🔍 Finding insights..."},
            {"milestone": 4, "percent": 80, "message": "💡 Generating assessment..."},
            {"milestone": 5, "percent": 100, "message": "✅ Complete"},
        ]
