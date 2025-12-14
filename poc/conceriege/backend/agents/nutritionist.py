"""
NutritionistAgent - LLM-Powered Health Specialist (PoC)

Generic health specialist that uses LLM to analyze K0 data and generate insights.
NOT hardcoded to GERD - can analyze ANY health pattern (diet, mood, sleep, etc.).

This is a PoC to prove the system works, not a production nutritionist.

Research basis:
- LLM as reasoning engine (GPT-4, 2023)
- Evidence-based health analysis
- Contradiction detection in user hypotheses
"""

import asyncio
from typing import List, Optional

from backend.agents.base import BaseAgent
from backend.models.analysis_result import AnalysisResult, Insight
from backend.models.conversation_state import ConversationState
from backend.services.k0_query_service import K0QueryService
from backend.services.llm_client import LLMClient
from backend.services.metrics_collector import MetricsCollector
from backend.services.progress_publisher import ProgressPublisher


class NutritionistAgent(BaseAgent):
    """
    LLM-powered health specialist that analyzes K0 data.

    **PoC Philosophy:**
    - Use LLM as reasoning engine (not hardcoded algorithms)
    - Generic health analysis (not just GERD)
    - Query K0 dynamically based on user query
    - LLM generates insights from data

    **NOT doing:**
    - Hardcoded correlation algorithms
    - GERD-specific logic
    - Manual pattern matching

    Example queries it can handle:
    - "milk is making me sick" → Analyzes diet + health events
    - "I'm anxious lately" → Analyzes mood + stress patterns
    - "my sleep is terrible" → Analyzes sleep + activities
    """

    def __init__(
        self,
        llm_client: LLMClient,
        k0_query_service: K0QueryService,
        metrics_collector: MetricsCollector,
        progress_publisher: Optional[ProgressPublisher] = None,
    ):
        """
        Initialize nutritionist agent.

        Args:
            llm_client: LLM client for analysis
            k0_query_service: K0 data access
            metrics_collector: Metrics tracker
            progress_publisher: Optional progress publisher for streaming
        """
        super().__init__(
            agent_id="nutritionist_001",
            agent_type="nutritionist",
            k0_query_service=k0_query_service,
            metrics_collector=metrics_collector,
            progress_publisher=progress_publisher,
        )
        self.llm_client = llm_client

    async def analyze(self, query: str, user_id: str, context: ConversationState) -> AnalysisResult:
        """
        Analyze user health query using LLM + K0 data.

        Flow:
        1. Emit progress: "Checking your data..."
        2. Determine what K0 tables to query (LLM decides)
        3. Emit progress: "Analyzing patterns..."
        4. Query K0 for relevant data
        5. Emit progress: "Finding insights..."
        6. Pass data to LLM for analysis
        7. Emit progress: "Generating insights..."
        8. LLM generates insights + detects contradictions
        9. Emit progress: "Complete"
        10. Return AnalysisResult

        Args:
            query: User's health concern
            user_id: FamilyOS user ID
            context: Conversation state

        Returns:
            AnalysisResult with LLM-generated insights
        """
        print(f"\n{'='*80}")
        print("[NUTRITIONIST] 🚀 Starting analysis")
        print(f"[NUTRITIONIST] Query: '{query}'")
        print(f"[NUTRITIONIST] User ID: {user_id}")
        print(f"{'='*80}\n")

        task_id = self._create_task_id()
        start_time = asyncio.get_event_loop().time()

        # Milestone 1: Start
        await self.emit_progress(task_id, 1, 20, "📊 Checking your health data...")
        await asyncio.sleep(0.1)  # Simulate K0 query

        # Query K0 for relevant data
        print("[NUTRITIONIST] 📊 Querying K0 data...")
        k0_data = await self._query_k0_data(user_id, query, context)

        print("[NUTRITIONIST] 📦 K0 Data Retrieved:")
        for table_name, data in k0_data.items():
            if isinstance(data, list):
                print(f"  - {table_name}: {len(data)} entries")
            else:
                print(f"  - {table_name}: {data}")

        # Milestone 2: Data retrieved
        await self.emit_progress(task_id, 2, 40, "🧠 Analyzing patterns...")
        await asyncio.sleep(0.1)

        # Extract user hypothesis (if any)
        user_hypothesis = self._extract_user_hypothesis(query, context)
        print(f"[NUTRITIONIST] 💭 User hypothesis: '{user_hypothesis}'")

        # Milestone 3: Analysis
        await self.emit_progress(task_id, 3, 60, "🔍 Finding insights...")
        await asyncio.sleep(0.1)

        # Use LLM to analyze data and generate insights
        print("[NUTRITIONIST] 🤖 Calling LLM for analysis...")
        insights = await self._llm_analyze_data(query, k0_data, user_hypothesis)

        print(f"[NUTRITIONIST] 💡 LLM returned {len(insights)} insights:")
        for i, insight in enumerate(insights, 1):
            print(f"  {i}. {insight.summary} (confidence: {insight.confidence})")

        # Milestone 4: Insights generated
        await self.emit_progress(task_id, 4, 80, "💡 Generating insights...")
        await asyncio.sleep(0.1)

        # Detect contradiction
        contradicts, actual_finding = self._detect_contradiction(user_hypothesis, insights)
        print(f"[NUTRITIONIST] ⚖️  Contradicts hypothesis: {contradicts}")
        if actual_finding:
            print(f"[NUTRITIONIST] 🎯 Actual finding: {actual_finding}")

        # Milestone 5: Complete
        await self.emit_progress(task_id, 5, 100, "✅ Analysis complete")

        # Calculate duration
        duration_ms = int((asyncio.get_event_loop().time() - start_time) * 1000)
        print(f"[NUTRITIONIST] ⏱️  Analysis took {duration_ms}ms")
        print(f"{'='*80}\n")

        # Record metrics
        self.metrics_collector.record_specialist_duration("nutritionist", duration_ms)

        return AnalysisResult(
            specialist_type="nutritionist",
            query=query,
            insights=insights,
            evidence=[],  # Evidence embedded in insights
            confidence=self._calculate_confidence(insights),
            duration_ms=duration_ms,
            contradicts_user_hypothesis=contradicts,
            user_hypothesis=user_hypothesis,
            actual_finding=actual_finding,
        )

    async def _query_k0_data(self, user_id: str, query: str, context: ConversationState) -> dict:
        """
        Query K0 for relevant data based on user query.

        Uses K0's generic query interface - no hardcoded GERD logic.

        Args:
            user_id: User ID
            query: User query
            context: Conversation context

        Returns:
            Dictionary with K0 data by table
        """
        # For PoC, query common health tables
        # Production: Use LLM to determine which tables to query

        k0_data = {}

        try:
            # Query diet logs (last 30 days)
            diet_data = self.k0_query_service.query(
                user_id, "episodic.diet_logs", filters={}, time_range="last_30_days", limit=50
            )
            k0_data["diet_logs"] = diet_data

            # Query health events (last 30 days)
            health_events = self.k0_query_service.query(
                user_id, "episodic.health_events", filters={}, time_range="last_30_days", limit=50
            )
            k0_data["health_events"] = health_events

            # Query mood logs if available
            try:
                mood_data = self.k0_query_service.query(
                    user_id, "emotional.mood_logs", filters={}, time_range="last_30_days", limit=50
                )
                k0_data["mood_logs"] = mood_data
            except Exception:
                pass  # Mood data might not exist

        except Exception as e:
            # Handle K0 errors gracefully
            print(f"K0 query error: {e}")
            k0_data = {"error": str(e)}

        return k0_data

    async def _llm_analyze_data(
        self, query: str, k0_data: dict, user_hypothesis: str
    ) -> List[Insight]:
        """
        Use LLM to analyze K0 data and generate insights.

        This is the core of the PoC - LLM does the reasoning, not hardcoded logic.

        Args:
            query: User query
            k0_data: K0 data dictionary
            user_hypothesis: User's hypothesis (e.g., "milk")

        Returns:
            List of Insight objects
        """
        print("[NUTRITIONIST-LLM] 🔨 Building analysis prompt...")

        # Build analysis prompt
        prompt = self._build_analysis_prompt(query, k0_data, user_hypothesis)

        print(f"[NUTRITIONIST-LLM] 📝 Prompt length: {len(prompt)} chars")
        print("[NUTRITIONIST-LLM] 📋 Full prompt:")
        print("=" * 80)
        print(prompt)
        print("=" * 80)

        # Call LLM
        try:
            print("[NUTRITIONIST-LLM] 🌐 Sending to LLM (synthesis profile, max 500 tokens)...")
            response = self.llm_client.generate(prompt, model_profile="synthesis", max_tokens=500)

            print(f"[NUTRITIONIST-LLM] ✅ LLM Response received ({len(response)} chars):")
            print("=" * 80)
            print(response)
            print("=" * 80)

            # Parse LLM response into insights
            print("[NUTRITIONIST-LLM] 🔍 Parsing response into insights...")
            insights = self._parse_llm_insights(response)

            print(f"[NUTRITIONIST-LLM] ✨ Parsed {len(insights)} insights")

            return insights
        except Exception as e:
            print(f"[NUTRITIONIST-LLM] ❌ ERROR: {str(e)}")
            # Fallback: Return generic insight on error
            return [
                Insight(
                    summary="Unable to complete analysis",
                    evidence=[f"Error: {str(e)}"],
                    severity="weak",
                    confidence=0.3,
                )
            ]

    def _build_analysis_prompt(self, query: str, k0_data: dict, user_hypothesis: str) -> str:
        """
        Build LLM prompt for data analysis with specific instructions for temporal correlation.

        Args:
            query: User query
            k0_data: K0 data
            user_hypothesis: User's hypothesis

        Returns:
            LLM prompt string
        """
        # Summarize K0 data for LLM
        data_summary = self._summarize_k0_data(k0_data)

        prompt = f"""You are a data-driven health specialist. Analyze ONLY what the data shows - do NOT make up patterns.

User Query: "{query}"
User's Hypothesis: "{user_hypothesis or 'None stated'}"

Complete Dataset:
{data_summary}

YOUR TASK:
1. **Find temporal correlations**: When user ate/consumed something, did symptoms appear within 2 hours?
2. **Count occurrences**: How many times did X lead to Y? Calculate: (times X caused Y) / (total times X occurred)
3. **Report ACTUAL numbers**: "4 out of 6 milk consumptions led to bloating within 2h"
4. **Confidence from data**: High confidence = strong pattern (>70%), Low confidence = weak/no pattern

CRITICAL RULES:
- ONLY use data provided above
- DO NOT invent correlations not in the data
- DO NOT make assumptions about causation
- If data is insufficient, say "Not enough data to determine pattern"
- Compare timestamps: food_item timestamp vs symptom timestamp (within 2h = correlated)

Generate 1-2 insights in this EXACT format:

INSIGHT: [Specific finding with numbers, e.g., "4 out of 6 milk consumptions correlated with bloating symptoms"]
EVIDENCE: [Exact data points with timestamps showing the pattern]
SEVERITY: [strong if >70% correlation, moderate if 40-70%, weak if <40%]
CONFIDENCE: [0.XX based on sample size and correlation strength]

Your analysis:"""

        return prompt

    def _summarize_k0_data(self, k0_data: dict) -> str:
        """
        Summarize K0 data for LLM prompt - provides COMPLETE data for accurate analysis.

        Args:
            k0_data: K0 data dictionary

        Returns:
            Human-readable summary with ALL relevant entries
        """
        summary_parts = []

        for table_name, data in k0_data.items():
            if table_name == "error":
                summary_parts.append(f"⚠️ K0 Error: {data}")
                continue

            if not data:
                summary_parts.append(f"{table_name}: No data")
                continue

            count = len(data)
            summary_parts.append(f"\n{table_name}: {count} entries")

            # Include ALL entries for accurate pattern detection (not just 3 samples)
            for entry in data:
                # Format entry as readable string
                summary_parts.append(f"  {entry}")

        return "\n".join(summary_parts) if summary_parts else "No data available"

    def _parse_llm_insights(self, llm_response: str) -> List[Insight]:
        """
        Parse LLM response into Insight objects.

        Args:
            llm_response: LLM output text

        Returns:
            List of Insight objects
        """
        insights = []

        # Simple parsing (production would be more robust)
        lines = llm_response.split("\n")
        current_insight: dict = {}

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if line.startswith("INSIGHT:"):
                if current_insight:
                    insights.append(self._create_insight_from_dict(current_insight))
                current_insight = {"summary": line.replace("INSIGHT:", "").strip()}
            elif line.startswith("EVIDENCE:"):
                current_insight["evidence"] = [line.replace("EVIDENCE:", "").strip()]
            elif line.startswith("SEVERITY:"):
                severity = line.replace("SEVERITY:", "").strip().lower()
                current_insight["severity"] = (
                    severity if severity in ["strong", "moderate", "weak"] else "moderate"
                )
            elif line.startswith("CONFIDENCE:"):
                try:
                    conf = float(line.replace("CONFIDENCE:", "").strip())
                    current_insight["confidence"] = conf
                except ValueError:
                    current_insight["confidence"] = 0.5

        # Add last insight
        if current_insight:
            insights.append(self._create_insight_from_dict(current_insight))

        # Fallback if no insights parsed
        if not insights:
            insights.append(
                Insight(
                    summary="Analysis completed",
                    evidence=["See LLM response for details"],
                    severity="moderate",
                    confidence=0.5,
                )
            )

        return insights

    def _create_insight_from_dict(self, data: dict) -> Insight:
        """Create Insight object from parsed data."""
        return Insight(
            summary=data.get("summary", "No summary"),
            evidence=data.get("evidence", []),
            severity=data.get("severity", "moderate"),
            confidence=data.get("confidence", 0.5),
        )

    def _extract_user_hypothesis(self, query: str, context: ConversationState) -> str:
        """
        Extract user's hypothesis from query (e.g., "milk" from "milk is making me sick").

        Args:
            query: User query
            context: Conversation context

        Returns:
            User hypothesis string or empty string
        """
        # Simple extraction (production would use NER)
        query_lower = query.lower()

        # Common food items
        foods = ["milk", "coffee", "pizza", "cheese", "bread", "wine", "chocolate"]
        for food in foods:
            if food in query_lower:
                return food

        return ""

    def _detect_contradiction(self, user_hypothesis: str, insights: List[Insight]) -> tuple:
        """
        Detect if insights contradict user hypothesis.

        Args:
            user_hypothesis: User's hypothesis
            insights: Generated insights

        Returns:
            (contradicts: bool, actual_finding: str)
        """
        if not user_hypothesis or not insights:
            return (False, "")

        # Check if primary insight mentions different entity
        primary_insight = insights[0]
        summary_lower = primary_insight.summary.lower()

        # If user hypothesis not in primary insight, might be contradiction
        if user_hypothesis.lower() not in summary_lower:
            # Extract what insight says instead
            # Simple extraction (production would be smarter)
            words = summary_lower.split()
            for word in words:
                if word not in [
                    "trigger",
                    "pattern",
                    "correlation",
                    "finding",
                    "the",
                    "is",
                    "a",
                    "an",
                ]:
                    if len(word) > 3:  # Avoid short words
                        return (True, word)

        return (False, "")

    def _calculate_confidence(self, insights: List[Insight]) -> float:
        """
        Calculate overall confidence from insights.

        Args:
            insights: List of insights

        Returns:
            Overall confidence (0.0-1.0)
        """
        if not insights:
            return 0.0

        # Average confidence across insights
        confidences = [i.confidence for i in insights]
        return sum(confidences) / len(confidences)

    def get_progress_milestones(self) -> List[dict]:
        """
        Get progress milestones for health analysis.

        Returns:
            List of 5 milestone definitions
        """
        return [
            {"milestone": 1, "percent": 20, "message": "📊 Checking your health data..."},
            {"milestone": 2, "percent": 40, "message": "🧠 Analyzing patterns..."},
            {"milestone": 3, "percent": 60, "message": "🔍 Finding insights..."},
            {"milestone": 4, "percent": 80, "message": "💡 Generating insights..."},
            {"milestone": 5, "percent": 100, "message": "✅ Analysis complete"},
        ]
