"""
Base class for Intelligent Writer Agents

These are AI-powered background agents (not static functions) that:
1. Subscribe to DeltaBus for SessionState deltas
2. Use Groq LLM to analyze deltas and extract meaning
3. Know P02/P05/P06 schemas for memory types
4. Have command port to decide what to write to K0
5. Batch writes via K0 Bridge BatchClient
"""

import json
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from importlib import import_module
from typing import Any, Dict, List

from l5_infrastructure.k0_bridge import BatchClient, Delta


def _get_logger(name: str):
    try:
        _structlog = import_module("structlog")
        return _structlog.get_logger(name)
    except Exception:

        class _ShimLogger:
            def __init__(self, n: str):
                self.name = n

            def debug(self, *args, **kwargs):
                pass

            def info(self, *args, **kwargs):
                pass

            def warning(self, *args, **kwargs):
                pass

            def error(self, *args, **kwargs):
                pass

        return _ShimLogger(name)


logger = _get_logger(__name__)


@dataclass
class WriterCommand:
    """Command from writer agent to K0."""

    command_id: str
    writer_type: str  # "memory", "learning", "semantic"
    delta_type: str  # "episodic", "prospective", "learning"
    content: Dict[str, Any]
    schema_version: str
    confidence: float  # 0.0-1.0 (LLM confidence)
    trace_id: str
    timestamp: int


class WriterCommandPort:
    """
    Command port for writer agents to send decisions to K0.

    Pattern: Writer decides what to write → sends command → batched to K0
    """

    def __init__(self, batch_client: BatchClient):
        """Initialize command port with K0 batch client."""
        self.batch_client = batch_client
        self.commands_processed = 0

    async def send_command(self, command: WriterCommand) -> bool:
        """
        Process writer command and batch to K0.

        Args:
            command: WriterCommand with write decision

        Returns:
            True if queued successfully
        """
        try:
            # Convert command to delta for batching
            delta = Delta(
                delta_id=command.command_id,
                delta_type=command.delta_type,
                content={
                    "writer_type": command.writer_type,
                    "data": command.content,
                    "confidence": command.confidence,
                    "schema_version": command.schema_version,
                },
                timestamp=command.timestamp,
                trace_id=command.trace_id,
            )

            # Send to batch client (will be flushed on 250ms/64KB/100 delta trigger)
            result = await self.batch_client.add_delta(delta)

            if result:
                self.commands_processed += 1
                logger.debug(
                    "writer_command_queued",
                    command_id=command.command_id,
                    writer_type=command.writer_type,
                    delta_type=command.delta_type,
                    confidence=command.confidence,
                )

            return result

        except Exception as e:
            logger.error("writer_command_error", command_id=command.command_id, error=str(e))
            return False


class WriterAgentBase(ABC):
    """
    Base class for intelligent writer agents.

    Each writer:
    - Subscribes to DeltaBus for SessionState deltas
    - Uses Groq LLM to understand and extract meaning
    - Sends decisions via command port
    - Maintains own extraction rules/schema knowledge
    """

    def __init__(
        self,
        agent_id: str,
        writer_type: str,  # "memory", "learning", "semantic"
        groq_client,  # GroqClient (avoid import cycle)
        batch_client: BatchClient,
        session_id: str,
    ):
        """
        Initialize writer agent.

        Args:
            agent_id: Unique agent identifier
            writer_type: Type of writer (memory, learning, semantic)
            groq_client: Groq LLM client
            batch_client: K0 Bridge batch client
            session_id: Current session ID
        """
        self.agent_id = agent_id
        self.writer_type = writer_type
        self.groq_client = groq_client
        self.command_port = WriterCommandPort(batch_client)
        self.session_id = session_id

        # State
        self.running = False
        self.deltas_processed = 0
        self.commands_sent = 0
        self.last_delta_time = time.time()

    # --------------------------------------------------------------------
    # Utility: Robust JSON extraction from LLM text outputs
    # --------------------------------------------------------------------
    def parse_json_from_text(self, text: str):
        """
        Extract a JSON object from LLM output text.

        Tries direct parse first; if that fails, attempts to locate the first
        balanced JSON object in the text (stripping code fences if present).

        Returns parsed object or raises ValueError if not found.
        """
        if text is None:
            raise ValueError("Empty LLM response text")

        s = text.strip()

        # Strip common fenced blocks
        if s.startswith("```"):
            # Remove first line fence and optional language tag
            s = re.sub(r"^```[a-zA-Z0-9_\-]*\n", "", s)
            # Remove trailing fence
            s = s.rstrip().removesuffix("```")

        # Fast path
        try:
            return json.loads(s)
        except Exception:
            pass

        # Heuristic: find first '{' and last '}'
        start = s.find("{")
        end = s.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = s[start : end + 1]
            try:
                return json.loads(candidate)
            except Exception:
                pass

        # Heuristic: remove leading commentary lines until JSON
        lines = s.splitlines()
        for i, line in enumerate(lines):
            if line.strip().startswith("{"):
                try:
                    return json.loads("\n".join(lines[i:]))
                except Exception:
                    break

        raise ValueError("Failed to parse JSON from LLM output")

    async def start(self):
        """Start writer agent - subscribe to DeltaBus."""
        self.running = True
        logger.info(
            "writer_agent_started",
            agent_id=self.agent_id,
            writer_type=self.writer_type,
        )

    async def stop(self):
        """Stop writer agent - unsubscribe from DeltaBus."""
        self.running = False
        logger.info(
            "writer_agent_stopped",
            agent_id=self.agent_id,
            deltas_processed=self.deltas_processed,
            commands_sent=self.commands_sent,
        )

    async def process_delta(
        self,
        delta: Dict[str, Any],
        session_state: Any,
        trace_id: str,
    ):
        """
        Process a single delta.

        Args:
            delta: SessionState delta
            session_state: Current session state (for context)
            trace_id: Trace ID for correlation
        """
        try:
            self.deltas_processed += 1
            self.last_delta_time = time.time()

            # Get extraction strategy for this delta type
            extraction_prompt = self._build_extraction_prompt(delta, session_state)

            # Use Groq LLM to analyze and extract
            decisions = await self._extract_with_llm(extraction_prompt, trace_id)

            # Send decisions as commands to K0
            for decision in decisions:
                command = WriterCommand(
                    command_id=f"cmd_{self.agent_id}_{int(time.time() * 1000)}",
                    writer_type=self.writer_type,
                    delta_type=decision["delta_type"],
                    content=decision["content"],
                    schema_version=decision["schema_version"],
                    confidence=decision.get("confidence", 0.8),
                    trace_id=trace_id,
                    timestamp=int(time.time() * 1000),
                )

                result = await self.command_port.send_command(command)
                if result:
                    self.commands_sent += 1

        except Exception as e:
            logger.error(
                "writer_process_delta_error",
                agent_id=self.agent_id,
                error=str(e),
                trace_id=trace_id,
            )

    @abstractmethod
    def _build_extraction_prompt(
        self,
        delta: Dict[str, Any],
        session_state: Any,
    ) -> str:
        """
        Build LLM prompt for delta extraction.

        Must be implemented by subclasses with writer-specific extraction rules.

        Args:
            delta: The delta to extract from
            session_state: Current session context

        Returns:
            LLM prompt string
        """
        pass

    @abstractmethod
    async def _extract_with_llm(
        self,
        prompt: str,
        trace_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Use Groq LLM to extract decisions from prompt.

        Must be implemented by subclasses.

        Args:
            prompt: Extraction prompt
            trace_id: Trace ID for logging

        Returns:
            List of extraction decisions (each with delta_type, content, confidence)
        """
        pass

    def get_status(self) -> Dict[str, Any]:
        """Get agent status."""
        return {
            "agent_id": self.agent_id,
            "writer_type": self.writer_type,
            "running": self.running,
            "deltas_processed": self.deltas_processed,
            "commands_sent": self.commands_sent,
            "last_delta_time": self.last_delta_time,
        }
