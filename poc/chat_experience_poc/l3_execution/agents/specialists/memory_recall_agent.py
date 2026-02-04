"""
MemoryRecallAgent - Tier 2 Specialist for Memory Recall & Life Wisdom.

Uses NATIVE LLM FUNCTION CALLING to query memory layers.

Handles:
  - Personal memory queries ("What did we discuss about Chicago?")
  - Relationship queries ("Who should I call about the trip?")
  - Emotional queries ("When was I happiest?")
  - Decision support ("What travel plans are pending?")
  - Life wisdom synthesis (advice based on memories)

Architecture:
  - Inherits from AgentBase
  - LLM decides which query_memory tool to call (native function calling)
  - Executes tool call against K0 PostgreSQL memory layers:
    * st_epi (episodic memories)
    * st_sem (semantic patterns)
    * st_kg_dom (knowledge graph entities)
    * st_social (relationships)
    * st_prospective (reminders/decisions)
    * st_observations (holistic context)
  - LLM synthesizes personalized answers from tool results
  - Supports multi-turn wisdom conversations

Flow:
  1. User query -> LLM with query_memory tool
  2. LLM calls query_memory(layers=["st_epi", "st_social"], search_term="travel", ...)
  3. Agent executes actual DB query
  4. Results returned to LLM for synthesis

References:
  - k0/deploy/scripts/validation/explore_memory_layers.py
  - docs/whiteboard/chat_experience.md - Memory recall vision
"""

import json
from typing import Any, Dict, List, Optional

import asyncpg
import structlog
from l3_execution.agents.agent_base import AgentBase

logger = structlog.get_logger(__name__)

# Database connection string
DB_URL = "postgresql://k0user:changeme@localhost:5432/k0_kernel"

# Tool definition for LLM function calling
QUERY_MEMORY_TOOL = {
    "name": "query_memory",
    "description": "Query K0 memory layers to recall personal memories, relationships, decisions, and life patterns. Use this to find information from the user's past.",
    "parameters": {
        "type": "object",
        "properties": {
            "layers": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Memory layers to query. Options: st_epi (events/episodes), st_sem (patterns), st_kg_dom (entities like people/places), st_social (relationships), st_prospective (decisions/reminders), st_observations (emotions/sentiment)",
            },
            "search_term": {
                "type": "string",
                "description": "Keyword to search for. Use 'all' to retrieve all records from a layer (for broad questions like 'what decisions do I have?' or 'who are my colleagues?'). Otherwise use a specific noun from the question (e.g., 'travel', 'Maya', 'Chicago').",
            },
            "query_type": {
                "type": "string",
                "description": "Type of query: 'relationship' (people), 'memory' (events), 'emotion' (feelings), 'decision' (plans/choices), 'location' (places), 'general'",
            },
        },
        "required": ["layers", "search_term"],
    },
}


class MemoryRecallAgent(AgentBase):
    """
    MemoryRecallAgent - Tier 2 Specialist for memory recall and life wisdom.

    Uses native LLM function calling to query memory layers.
    USER-FACING: Synthesizes personalized answers from memory layers.
    """

    def __init__(
        self,
        agent_id: str,
        session_id: str,
        groq_client,
        trace_id: Optional[str] = None,
        mailbox: Optional[Any] = None,
    ):
        """Initialize MemoryRecallAgent."""
        super().__init__(
            agent_id=agent_id,
            agent_type="memory_recall",
            session_id=session_id,
            groq_client=groq_client,
            mailbox=mailbox,
            trace_id=trace_id,
        )

        self._db_pool: Optional[asyncpg.Pool] = None
        self._conversation_context: List[Dict[str, str]] = []

        logger.info(
            "memory_recall_agent_initialized",
            agent_id=agent_id,
            session_id=session_id,
            trace_id=trace_id,
        )

    async def _get_db_connection(self) -> asyncpg.Connection:
        """Get database connection."""
        if self._db_pool is None:
            self._db_pool = await asyncpg.create_pool(DB_URL, min_size=1, max_size=5)
        return await self._db_pool.acquire()

    async def _release_connection(self, conn: asyncpg.Connection):
        """Release database connection."""
        if self._db_pool:
            await self._db_pool.release(conn)

    async def process_message(self, message: Dict[str, Any]):
        """
        Process memory recall query using LLM function calling.

        Args:
            message: Contains "query" (user question) and optional "turn" (1 or 2)
        """
        query = message.get("query", "")
        turn = message.get("turn", 1)

        logger.info(
            "memory_recall_processing",
            query=query,
            turn=turn,
            agent_id=self.agent_id,
            trace_id=self.trace_id,
        )

        if turn == 1:
            # First turn: Use LLM tool calling to query memories
            return await self._process_memory_query_with_tools(query)
        else:
            # Second turn: Provide wisdom based on context
            return await self._process_wisdom_request(query)

    async def _process_memory_query_with_tools(self, query: str) -> Dict[str, Any]:
        """
        Process memory query using LLM native function calling.

        Flow:
        1. Send query to LLM with query_memory tool
        2. LLM decides tool call parameters
        3. Execute tool (actual DB query)
        4. Return results to LLM for synthesis
        """
        # Step 1: Ask LLM to decide which memory layers to query
        system_prompt = """You are a personal AI assistant with access to the user's memory layers.
When the user asks a question, use the query_memory tool to find relevant information.

Choose layers based on the question:
- st_epi: For events, what happened, experiences
- st_social: For people, relationships, colleagues, family
- st_prospective: For decisions, plans, reminders, travel plans, pending items
- st_kg_dom: For entities like places, things, topics
- st_sem: For patterns and learned facts
- st_observations: For emotions and feelings

IMPORTANT for search_term:
- For BROAD questions like "what decisions do I have?", "who are my colleagues?", "what are my plans?" -> use search_term="all"
- For SPECIFIC questions like "tell me about Maya" or "what about the Chicago trip" -> use the specific noun

Pick 1-2 most relevant layers. Use 'all' for broad listing questions."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
        ]

        # Step 2: Call LLM with tool
        response = await self.groq_client.complete_with_tools(
            messages=messages,
            tools=[QUERY_MEMORY_TOOL],
            agent_type="memory_recall",
            temperature=0.2,
            max_tokens=300,
            trace_id=self.trace_id,
        )

        logger.info(
            "llm_tool_response",
            tool_calls=response.get("tool_calls", []),
            has_content=bool(response.get("content")),
            trace_id=self.trace_id,
        )

        # Step 3: Execute tool calls if any
        memory_context = {}
        tool_calls = response.get("tool_calls", [])

        if tool_calls:
            for tool_call in tool_calls:
                if tool_call.get("name") == "query_memory":
                    args = tool_call.get("args", {})
                    layers = args.get("layers", ["st_epi", "st_social"])
                    search_term = args.get("search_term", query.split()[0])
                    query_type = args.get("query_type", "general")

                    logger.info(
                        "executing_tool_call",
                        tool="query_memory",
                        layers=layers,
                        search_term=search_term,
                        query_type=query_type,
                        trace_id=self.trace_id,
                    )

                    # Execute actual DB query
                    memory_context = await self._execute_memory_query(
                        layers=layers,
                        search_term=search_term,
                    )
        else:
            # Fallback: LLM didn't call tool, use defaults
            logger.warning(
                "no_tool_call_fallback",
                query=query,
                trace_id=self.trace_id,
            )
            memory_context = await self._execute_memory_query(
                layers=["st_epi", "st_social", "st_prospective"],
                search_term=query.split()[0] if query else "life",
            )

        # Step 4: Synthesize answer using LLM
        answer = await self._synthesize_answer(query, memory_context)

        # Store context for turn 2
        self._conversation_context.append(
            {
                "query": query,
                "memory_context": memory_context,
                "answer": answer,
                "tool_calls": tool_calls,
            }
        )

        return {
            "answer": answer,
            "memory_sources": list(memory_context.keys()),
            "tool_calls": tool_calls,
            "context_stored": True,
        }

    async def _execute_memory_query(
        self, layers: List[str], search_term: str
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Execute actual database query based on LLM's tool call.

        This is the tool execution - called when LLM decides to use query_memory.
        """
        results = {}
        conn = await self._get_db_connection()

        try:
            for layer in layers:
                if layer == "st_epi":
                    results["episodic"] = await self._query_episodic(conn, search_term)
                elif layer == "st_sem":
                    results["semantic"] = await self._query_semantic(conn, search_term)
                elif layer == "st_kg_dom":
                    results["entities"] = await self._query_knowledge_graph(conn, search_term)
                elif layer == "st_social":
                    results["relationships"] = await self._query_social(conn, search_term)
                elif layer == "st_prospective":
                    results["intentions"] = await self._query_prospective(conn, search_term)
                elif layer == "st_observations":
                    results["observations"] = await self._query_observations(conn, search_term)

            logger.info(
                "memory_query_executed",
                layers=layers,
                search_term=search_term,
                result_counts={k: len(v) for k, v in results.items()},
                trace_id=self.trace_id,
            )

        finally:
            await self._release_connection(conn)

        return results

    async def _query_episodic(
        self, conn: asyncpg.Connection, search_term: str
    ) -> List[Dict[str, Any]]:
        """Query episodic memories (st_epi)."""
        # Handle 'all' or empty search term - retrieve all records
        if search_term.lower() in ("all", "", "*"):
            rows = await conn.fetch(
                """
                SELECT episode_id, episode_summary, episode_type,
                       primary_location, participants_json, source_texts_json
                FROM st_epi
                ORDER BY created_at DESC
                LIMIT 10
                """
            )
        else:
            rows = await conn.fetch(
                """
                SELECT episode_id, episode_summary, episode_type,
                       primary_location, participants_json, source_texts_json
                FROM st_epi
                WHERE episode_summary ILIKE $1
                   OR source_texts_json ILIKE $1
                   OR participants_json ILIKE $1
                ORDER BY created_at DESC
                LIMIT 5
                """,
                f"%{search_term}%",
            )

        return [
            {
                "summary": r["episode_summary"],
                "type": r["episode_type"],
                "location": r["primary_location"],
                "participants": r["participants_json"],
                "source": self._extract_first_text(r["source_texts_json"]),
            }
            for r in rows
        ]

    async def _query_semantic(
        self, conn: asyncpg.Connection, search_term: str
    ) -> List[Dict[str, Any]]:
        """Query semantic patterns (st_sem)."""
        # Handle 'all' or empty search term - retrieve all records
        if search_term.lower() in ("all", "", "*"):
            rows = await conn.fetch(
                """
                SELECT pattern_name, pattern_description, pattern_type,
                       source_texts_json, confidence_score
                FROM st_sem
                ORDER BY confidence_score DESC
                LIMIT 10
                """
            )
        else:
            rows = await conn.fetch(
                """
                SELECT pattern_name, pattern_description, pattern_type,
                       source_texts_json, confidence_score
                FROM st_sem
                WHERE pattern_name ILIKE $1
                   OR pattern_description ILIKE $1
                   OR source_texts_json ILIKE $1
                ORDER BY confidence_score DESC
                LIMIT 5
                """,
                f"%{search_term}%",
            )

        return [
            {
                "pattern": r["pattern_name"],
                "description": r["pattern_description"],
                "type": r["pattern_type"],
                "confidence": float(r["confidence_score"]) if r["confidence_score"] else 0,
            }
            for r in rows
        ]

    async def _query_knowledge_graph(
        self, conn: asyncpg.Connection, search_term: str
    ) -> List[Dict[str, Any]]:
        """Query knowledge graph entities (st_kg_dom)."""
        # Handle 'all' or empty search term - retrieve all records
        if search_term.lower() in ("all", "", "*"):
            rows = await conn.fetch(
                """
                SELECT canonical_name, entity_type, attributes_json,
                       source_texts_json, observation_count
                FROM st_kg_dom
                ORDER BY observation_count DESC
                LIMIT 15
                """
            )
        else:
            rows = await conn.fetch(
                """
                SELECT canonical_name, entity_type, attributes_json,
                       source_texts_json, observation_count
                FROM st_kg_dom
                WHERE canonical_name ILIKE $1
                   OR source_texts_json ILIKE $1
                ORDER BY observation_count DESC
                LIMIT 10
                """,
                f"%{search_term}%",
            )

        return [
            {
                "name": r["canonical_name"],
                "type": r["entity_type"],
                "mentions": r["observation_count"],
                "source": self._extract_first_text(r["source_texts_json"]),
            }
            for r in rows
        ]

    async def _query_social(
        self, conn: asyncpg.Connection, search_term: str
    ) -> List[Dict[str, Any]]:
        """Query social relationships (st_social)."""
        # Handle 'all' or empty search term - retrieve all records
        if search_term.lower() in ("all", "", "*"):
            rows = await conn.fetch(
                """
                SELECT relationship_label, relationship_type, interaction_count,
                       source_texts_json, dominant_emotion
                FROM st_social
                ORDER BY interaction_count DESC
                LIMIT 10
                """
            )
        else:
            rows = await conn.fetch(
                """
                SELECT relationship_label, relationship_type, interaction_count,
                       source_texts_json, dominant_emotion
                FROM st_social
                WHERE relationship_label ILIKE $1
                   OR source_texts_json ILIKE $1
                ORDER BY interaction_count DESC
                LIMIT 5
                """,
                f"%{search_term}%",
            )

        return [
            {
                "person": r["relationship_label"],
                "type": r["relationship_type"],
                "interactions": r["interaction_count"],
                "emotion": r["dominant_emotion"],
                "source": self._extract_first_text(r["source_texts_json"]),
            }
            for r in rows
        ]

    async def _query_prospective(
        self, conn: asyncpg.Connection, search_term: str
    ) -> List[Dict[str, Any]]:
        """Query prospective memories - reminders and decisions (st_prospective)."""
        # Handle 'all' or empty search term - retrieve all records
        if search_term.lower() in ("all", "", "*"):
            rows = await conn.fetch(
                """
                SELECT intention_description, intention_type, status,
                       source_texts_json, confidence_score
                FROM st_prospective
                ORDER BY created_at DESC
                LIMIT 10
                """
            )
        else:
            rows = await conn.fetch(
                """
                SELECT intention_description, intention_type, status,
                       source_texts_json, confidence_score
                FROM st_prospective
                WHERE intention_description ILIKE $1
                   OR source_texts_json ILIKE $1
                ORDER BY created_at DESC
                LIMIT 5
                """,
                f"%{search_term}%",
            )

        return [
            {
                "intention": r["intention_description"],
                "type": r["intention_type"],
                "status": r["status"],
                "confidence": float(r["confidence_score"]) if r["confidence_score"] else 0,
            }
            for r in rows
        ]

    async def _query_observations(
        self, conn: asyncpg.Connection, search_term: str
    ) -> List[Dict[str, Any]]:
        """Query observations for emotional/temporal context."""
        rows = await conn.fetch(
            """
            SELECT layer, sentiment_score, dominant_emotion,
                   circadian_slot, is_weekend, salience_score
            FROM st_observations
            WHERE dominant_emotion IS NOT NULL
            ORDER BY salience_score DESC
            LIMIT 10
            """
        )

        return [
            {
                "layer": r["layer"],
                "sentiment": float(r["sentiment_score"]) if r["sentiment_score"] else 0,
                "emotion": r["dominant_emotion"],
                "time_slot": r["circadian_slot"],
                "weekend": r["is_weekend"],
            }
            for r in rows
        ]

    def _extract_first_text(self, source_texts_json: Optional[str]) -> Optional[str]:
        """Extract first text from source_texts_json."""
        if not source_texts_json:
            return None
        try:
            texts = json.loads(source_texts_json)
            if texts and isinstance(texts, list):
                return texts[0][:150] if len(texts[0]) > 150 else texts[0]
        except Exception:
            pass
        return None

    async def _synthesize_answer(
        self, query: str, memory_context: Dict[str, List[Dict[str, Any]]]
    ) -> str:
        """
        Use LLM to synthesize a personalized answer from memory context.
        """
        # Build context string
        context_parts = []

        if memory_context.get("episodic"):
            context_parts.append("EPISODIC MEMORIES (What happened):")
            for m in memory_context["episodic"]:
                context_parts.append(
                    f"  - {m['summary']} at {m['location']} with {m['participants']}"
                )

        if memory_context.get("relationships"):
            context_parts.append("\nRELATIONSHIPS:")
            for r in memory_context["relationships"]:
                context_parts.append(
                    f"  - {r['person']} ({r['type']}): {r['interactions']} interactions, emotion: {r['emotion']}"
                )

        if memory_context.get("entities"):
            context_parts.append("\nENTITIES IN YOUR LIFE:")
            for e in memory_context["entities"]:
                context_parts.append(
                    f"  - {e['name']} ({e['type']}): mentioned {e['mentions']} times"
                )

        if memory_context.get("intentions"):
            context_parts.append("\nPENDING INTENTIONS/DECISIONS:")
            for i in memory_context["intentions"]:
                context_parts.append(f"  - [{i['type']}] {i['intention']} (status: {i['status']})")

        if memory_context.get("semantic"):
            context_parts.append("\nPATTERNS LEARNED:")
            for s in memory_context["semantic"]:
                context_parts.append(f"  - {s['pattern']}: {s['description']}")

        context_str = "\n".join(context_parts) if context_parts else "No specific memories found."

        prompt = f"""You are a personal AI assistant with access to the user's memories.

USER QUESTION: "{query}"

MEMORIES FROM YOUR LIFE:
{context_str}

Based on these memories, provide a warm, personalized answer. Be specific and reference actual memories when possible. If no relevant memories found, say so honestly.

Keep your answer conversational and helpful (2-4 sentences)."""

        response = await self.call_llm(
            user_input=prompt,
            context_data={"memory_count": sum(len(v) for v in memory_context.values())},
            temperature=0.7,
            max_tokens=500,
        )

        return response.get("content", "I couldn't find relevant memories to answer that.")

    async def _process_wisdom_request(self, query: str) -> Dict[str, Any]:
        """
        Process second-turn wisdom request.

        Uses accumulated context to provide life advice.
        """
        if not self._conversation_context:
            return {
                "answer": "I need some context first. What would you like to know about?",
                "wisdom": False,
            }

        # Get accumulated context
        context_summary = self._build_context_summary()

        # Generate wisdom using LLM
        wisdom = await self._generate_wisdom(query, context_summary)

        return {
            "answer": wisdom,
            "wisdom": True,
            "based_on_memories": len(self._conversation_context),
        }

    def _build_context_summary(self) -> str:
        """Build summary of conversation context for wisdom generation."""
        parts = []
        for ctx in self._conversation_context:
            parts.append(f"Q: {ctx['query']}")
            parts.append(f"A: {ctx['answer']}")
            if ctx.get("memory_context"):
                memory_count = sum(len(v) for v in ctx["memory_context"].values())
                parts.append(f"(Based on {memory_count} memories)")
            if ctx.get("tool_calls"):
                tc = ctx["tool_calls"][0] if ctx["tool_calls"] else {}
                parts.append(f"(Queried: {tc.get('args', {}).get('layers', [])})")
        return "\n".join(parts)

    async def _generate_wisdom(self, query: str, context_summary: str) -> str:
        """
        Generate life wisdom based on accumulated context.
        """
        prompt = f"""You are a wise personal AI assistant reflecting on the user's life.

PREVIOUS CONVERSATION:
{context_summary}

USER NOW ASKS FOR WISDOM: "{query}"

Based on the memories and context shared, provide thoughtful life advice. Be warm, insightful, and grounded in what you know about their life. Draw connections between their experiences and offer meaningful perspective.

Keep your wisdom response to 4-6 sentences."""

        response = await self.call_llm(
            user_input=prompt,
            context_data={"wisdom_mode": True},
            temperature=0.7,
            max_tokens=1200,
        )

        return response.get("content", "Let me reflect on that...")

    async def cleanup(self):
        """Cleanup database connections."""
        if self._db_pool:
            await self._db_pool.close()
            self._db_pool = None
