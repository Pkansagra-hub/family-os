"""
Nutritionist Specialist Agent - Analyzes dietary patterns and queries K0
"""

import asyncio
import logging
from typing import Any, Dict

from groq import AsyncGroq

from config.settings import settings
from contracts.messages import (
    JobClarification,
    JobClarificationResponse,
    JobProgress,
    JobRequest,
    JobResult,
)
from l5_infrastructure.handoff_space import get_handoff_space
from l5_infrastructure.k0_bridge import get_k0_bridge

logger = logging.getLogger(__name__)


class NutritionistSpecialist:
    """
    Nutritionist Specialist:
    - Listens for job requests
    - May request up to 2 clarifications
    - Queries K0 for dietary patterns
    - Compiles findings and returns results
    """

    def __init__(self):
        self.client = AsyncGroq(api_key=settings.groq_api_key)
        self.handoff = get_handoff_space()
        self.k0_bridge = get_k0_bridge()

        self.system_prompt = """You are a Nutritionist Specialist in the family health assistant system.

Your expertise:
- Dietary patterns and food sensitivities
- Nutritional analysis and recommendations
- Identifying potential food triggers
- Interpreting health symptoms related to diet

Your workflow:
1. Analyze the query to understand what information you need
2. If symptom details are unclear, ask up to 2 clarifying questions
3. Query the K0 memory system for relevant dietary history
4. Compile findings with confidence levels and recommendations

Be thorough but concise. Focus on actionable insights."""

        # Active jobs
        self.active_jobs: Dict[str, Dict[str, Any]] = {}

    async def start_listening(self):
        """Start listening for job requests"""
        logger.info("[Nutritionist] Starting to listen for job requests")

        # Subscribe to wildcard for all job requests
        request_queue = self.handoff.subscribe("job.request.*")

        while True:
            try:
                job_request: JobRequest = await request_queue.get()

                # Check if this is for us
                if job_request.specialist_name.lower() == "nutritionist":
                    logger.info(f"[Nutritionist] Picked up job for thread {job_request.thread_id}")

                    # Process job in background
                    asyncio.create_task(self._process_job(job_request))

            except Exception as e:
                logger.error(f"[Nutritionist] Error in listener: {e}")
                await asyncio.sleep(1)

    async def _process_job(self, job_request: JobRequest):
        """Process a job request"""
        thread_id = job_request.thread_id

        # Initialize job tracking
        self.active_jobs[thread_id] = {
            "request": job_request,
            "clarifications": [],
            "clarification_count": 0,
        }

        try:
            # Step 1: Analyze if we need clarification
            await self._send_progress(thread_id, "Analyzing your query...")

            needs_clarification = await self._analyze_query(job_request)

            # Step 2: Request clarifications if needed (up to 2)
            symptom_type = None
            if (
                needs_clarification
                and self.active_jobs[thread_id]["clarification_count"]
                < settings.clarification_limit
            ):
                symptom_type = await self._request_clarifications(thread_id, job_request)
            else:
                # Infer from query
                symptom_type = await self._infer_symptom_type(job_request.query)

            # Step 3: Query K0 for patterns
            await self._send_progress(thread_id, "Checking your dietary history...")

            k0_data = await self.k0_bridge.query_combined(
                query=job_request.query,
                symptom_type=symptom_type or "general",
                context=job_request.context,
            )

            # Step 4: Compile findings
            await self._send_progress(thread_id, "Analyzing patterns...")

            findings = await self._compile_findings(job_request, k0_data)

            # Step 5: Send result
            result = JobResult(
                thread_id=thread_id,
                specialist_name="nutritionist",
                findings=findings["summary"],
                confidence=findings["confidence"],
                sources=findings["sources"],
            )

            await self.handoff.publish(f"job.result.{thread_id}", result)
            logger.info(f"[Nutritionist] Completed job for thread {thread_id}")

        except Exception as e:
            logger.error(f"[Nutritionist] Error processing job: {e}")

            # Send error result
            result = JobResult(
                thread_id=thread_id,
                specialist_name="nutritionist",
                findings=f"I encountered an error analyzing your dietary patterns: {str(e)}",
                confidence=0.0,
                sources=[],
            )
            await self.handoff.publish(f"job.result.{thread_id}", result)

        finally:
            # Cleanup
            self.active_jobs.pop(thread_id, None)

    async def _analyze_query(self, job_request: JobRequest) -> bool:
        """Determine if clarification is needed"""

        prompt = f"""Query: "{job_request.query}"

Analyze if you need clarification to provide accurate dietary analysis.

Do you need to know:
- Type of symptoms (headache, stomach issues, nausea, etc.)?
- Timing or frequency?
- Severity?

Respond: NEED_CLARIFICATION: yes/no"""

        try:
            response = await self.client.chat.completions.create(
                model=settings.groq_model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=50,
            )

            content = response.choices[0].message.content
            needs = "yes" in content.lower()
            logger.info(f"[Nutritionist] Needs clarification: {needs}")
            return needs

        except Exception as e:
            logger.error(f"[Nutritionist] Error analyzing query: {e}")
            return True  # Default to asking for clarification

    async def _request_clarifications(self, thread_id: str, job_request: JobRequest) -> str:
        """Request clarifications from user via Proactive agent"""

        job = self.active_jobs[thread_id]

        # First clarification: symptom type
        if job["clarification_count"] == 0:
            question = "What kind of symptoms do you experience? For example: stomach issues, headaches, nausea, or something else?"

            clarification = JobClarification(
                thread_id=thread_id,
                specialist_name="nutritionist",
                question=question,
                clarification_round=1,
            )

            await self.handoff.publish(f"job.clarification.{thread_id}", clarification)
            job["clarification_count"] += 1

            # Wait for response
            response_queue = self.handoff.subscribe(f"job.clarification_response.{thread_id}")

            try:
                response: JobClarificationResponse = await asyncio.wait_for(
                    response_queue.get(), timeout=30.0
                )

                job["clarifications"].append({"question": question, "answer": response.answer})

                logger.info(f"[Nutritionist] Received clarification: {response.answer}")
                return response.answer

            except asyncio.TimeoutError:
                logger.warning("[Nutritionist] Clarification timeout")
                return "general"

        return "general"

    async def _infer_symptom_type(self, query: str) -> str:
        """Infer symptom type from query if clarification wasn't needed"""

        query_lower = query.lower()

        if any(word in query_lower for word in ["stomach", "bloat", "digest", "cramp"]):
            return "stomach"
        elif any(word in query_lower for word in ["head", "migraine"]):
            return "headache"
        elif any(word in query_lower for word in ["nausea", "sick", "vomit"]):
            return "nausea"
        else:
            return "general"

    async def _compile_findings(
        self, job_request: JobRequest, k0_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Compile findings from K0 data"""

        episodic = k0_data["episodic_memories"]
        semantic = k0_data["semantic_pattern"]

        # Build summary using LLM
        prompt = f"""Based on dietary analysis:

Query: {job_request.query}

Past Events (Episodic Memory):
{self._format_episodic(episodic)}

Pattern Analysis:
- Pattern: {semantic.get('pattern', 'unknown')}
- Confidence: {semantic.get('confidence', 0.0)}
- Triggers: {', '.join(semantic.get('triggers', []))}
- Frequency: {semantic.get('frequency', 'unknown')}
- Severity: {semantic.get('severity', 'unknown')}

Recommendations:
{self._format_recommendations(semantic.get('recommendations', []))}

Compile this into a clear, empathetic summary (2-3 sentences) that:
1. States the likely pattern
2. References specific past occurrences
3. Provides 1-2 key recommendations

Summary:"""

        try:
            response = await self.client.chat.completions.create(
                model=settings.groq_model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.6,
                max_tokens=300,
            )

            summary = response.choices[0].message.content

            return {
                "summary": summary,
                "confidence": semantic.get("confidence", 0.5),
                "sources": [
                    f"Episodic memory: {len(episodic)} events",
                    f"Pattern: {semantic.get('pattern')}",
                ],
            }

        except Exception as e:
            logger.error(f"[Nutritionist] Error compiling findings: {e}")
            return {
                "summary": f"Based on {len(episodic)} past mentions and pattern analysis, {semantic.get('pattern', 'dietary sensitivity')} detected.",
                "confidence": semantic.get("confidence", 0.5),
                "sources": ["K0 memory"],
            }

    def _format_episodic(self, memories: list[Dict[str, Any]]) -> str:
        """Format episodic memories for prompt"""
        if not memories:
            return "No specific past events found."

        formatted = []
        for mem in memories[:3]:  # Limit to 3 most relevant
            formatted.append(f"- {mem['date']}: {mem['entry']}")

        return "\n".join(formatted)

    def _format_recommendations(self, recommendations: list[str]) -> str:
        """Format recommendations for prompt"""
        if not recommendations:
            return "No specific recommendations available."

        return "\n".join(f"- {rec}" for rec in recommendations)

    async def _send_progress(self, thread_id: str, message: str):
        """Send progress update"""
        progress = JobProgress(
            thread_id=thread_id,
            specialist_name="nutritionist",
            status="in_progress",
            message=message,
        )

        await self.handoff.publish(f"job.progress.{thread_id}", progress)
