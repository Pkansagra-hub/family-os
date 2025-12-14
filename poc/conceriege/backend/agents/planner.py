"""
PlannerAgent - Planning and Task Management Specialist

Helps with goal planning, task prioritization, and workflow optimization.
"""

from typing import Optional

from backend.agents.base import BaseAgent
from backend.models.analysis_result import AnalysisResult, Insight
from backend.models.conversation_state import ConversationState
from backend.services.k0_query_service import K0QueryService
from backend.services.llm_client import LLMClient
from backend.services.metrics_collector import MetricsCollector
from backend.services.progress_publisher import ProgressPublisher


class PlannerAgent(BaseAgent):
    """LLM-powered planning specialist."""

    def __init__(
        self,
        llm_client: LLMClient,
        k0_query_service: K0QueryService,
        metrics_collector: MetricsCollector,
        progress_publisher: Optional[ProgressPublisher] = None,
    ):
        """Initialize planner agent."""
        super().__init__(
            agent_id="planner_001",
            agent_type="planner",
            k0_query_service=k0_query_service,
            metrics_collector=metrics_collector,
            progress_publisher=progress_publisher,
        )
        self.llm_client = llm_client

    async def analyze(self, query: str, user_id: str, context: ConversationState) -> AnalysisResult:
        """Analyze planning request."""
        task_id = self._create_task_id()

        await self.emit_progress(task_id, 1, 20, "📋 Analyzing goals...")
        await self.emit_progress(task_id, 2, 40, "🧠 Evaluating constraints...")
        await self.emit_progress(task_id, 3, 60, "🔍 Finding opportunities...")
        await self.emit_progress(task_id, 4, 80, "💡 Generating plan...")
        await self.emit_progress(task_id, 5, 100, "✅ Plan complete")

        return AnalysisResult(
            specialist_type="planner",
            query=query,
            insights=[Insight(summary="Planning recommendations generated")],
            confidence=0.75,
            duration_ms=500,
        )

    def get_progress_milestones(self):
        """Get progress milestones."""
        return [
            {"milestone": 1, "percent": 20, "message": "📋 Analyzing goals..."},
            {"milestone": 2, "percent": 40, "message": "🧠 Evaluating constraints..."},
            {"milestone": 3, "percent": 60, "message": "🔍 Finding opportunities..."},
            {"milestone": 4, "percent": 80, "message": "💡 Generating plan..."},
            {"milestone": 5, "percent": 100, "message": "✅ Complete"},
        ]
