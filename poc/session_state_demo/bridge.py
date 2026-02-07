"""
SessionLLMBridge - Connects SessionStateManager to LLM Conversations
=====================================================================

EPIC: 1 - Session State Wrapper Layer
ISSUES: 1.1, 1.2, 1.3

Responsibilities:
- Automatic writes: Turn history, telemetry, meta updates
- Context building: Read state to build LLM prompts
- Tool execution: Apply LLM tool calls to session state

Architecture:
    User Input
        |
        v
    SessionLLMBridge
        |
        +---> auto_record_user_turn() ---> history_active, telemetry
        |
        +---> build_context() <--- history_active, persona, affective_now
        |
        v
    GoogleClient.complete_with_tools()
        |
        v
    SessionLLMBridge
        |
        +---> execute_tool_calls() ---> persona, affective_now, beliefs_active
        |
        +---> auto_record_assistant_turn() ---> history_active
        |
        v
    Response to User
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from k1.sessionstate.factory import SessionStateFactory
from k1.sessionstate.manager import SessionStateManager

# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class TurnRecord:
    """Record of a conversation turn for display."""

    turn_number: int
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    duration_ms: int = 0
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    tokens_used: int = 0


@dataclass
class StateChange:
    """Record of a session state change for display."""

    section: str
    operation: str
    description: str
    bytes_delta: int = 0
    success: bool = True
    auto: bool = True  # True = automatic, False = LLM tool


@dataclass
class BridgeStats:
    """Statistics about the bridge session."""

    total_turns: int = 0
    user_turns: int = 0
    assistant_turns: int = 0
    tool_calls_executed: int = 0
    tool_calls_rejected: int = 0  # Blocked by write gate
    total_latency_ms: int = 0
    checkpoints_created: int = 0
    restores_performed: int = 0
    bytes_saved_by_gate: int = 0  # Estimated savings from dedup

    # Latency SLO tracking
    turn_latencies_ms: List[int] = field(default_factory=list)  # Per-turn latencies
    slo_violations: int = 0  # Turns exceeding SLO


# =============================================================================
# LATENCY SLO/SLI CONFIGURATION (K1 Architecture Targets)
# =============================================================================


@dataclass
class LatencySLO:
    """
    Latency SLO/SLI definitions from K1 architecture.

    Reference: k1_cognitive_architecture_skeleton.mmd
    - LOW tier: <2s (simple tool + response)
    - MEDIUM tier: 2-10s (LLM reasoning + execution)
    - HIGH tier: 10-60s (planning + execution)

    This demo operates at roughly MEDIUM tier complexity.
    """

    # SLO targets (milliseconds)
    p50_target_ms: int = 1500  # 50th percentile target
    p95_target_ms: int = 3000  # 95th percentile target
    p99_target_ms: int = 5000  # 99th percentile target
    max_acceptable_ms: int = 10000  # Hard limit

    # Component budgets (from architecture)
    sessionstate_read_ms: int = 1  # <1ms read latency
    context_build_ms: int = 50  # Context compilation
    llm_call_ms: int = 2000  # LLM response (external)
    tool_execution_ms: int = 100  # Per tool
    state_write_ms: int = 10  # State mutations

    def evaluate(self, latency_ms: int) -> str:
        """Evaluate latency against SLO. Returns 'OK', 'WARN', or 'BREACH'."""
        if latency_ms <= self.p50_target_ms:
            return "OK"
        elif latency_ms <= self.p95_target_ms:
            return "WARN"
        else:
            return "BREACH"


DEFAULT_SLO = LatencySLO()


# =============================================================================
# SYSTEM PROMPT BUILDER
# =============================================================================


SYSTEM_PROMPT_TEMPLATE = """You are a helpful family assistant. You remember context from our conversation and learn user preferences.

{persona_context}

{history_context}

{emotional_context}

IMPORTANT: When you learn something new about the user (preferences, family info, interests, constraints), use the appropriate tool to record it. This helps you remember for future conversations.

Available tools:
- update_persona: Record user preferences, interests, or personal information
- update_emotion: Track the emotional tone of the conversation
- add_belief: Record facts you've learned about the user

Be warm, helpful, and conversational. Ask clarifying questions when needed."""


# =============================================================================
# SESSION LLM BRIDGE
# =============================================================================


class SessionLLMBridge:
    """
    Bridge connecting SessionStateManager to LLM conversations.

    Handles:
    - Automatic turn recording (history_active, telemetry)
    - Context building for LLM prompts
    - Tool call execution to update session state
    - Checkpoint/restore lifecycle management

    Usage:
        bridge = SessionLLMBridge(session_id="demo-001")
        bridge.start()

        # Process a turn
        bridge.record_user_turn("Hello, I'm planning a trip")
        context = bridge.build_llm_context()
        # ... call LLM with context ...
        bridge.execute_tool_calls(tool_calls)
        bridge.record_assistant_turn(response, duration_ms)

        bridge.checkpoint()
        bridge.stop()
    """

    def __init__(
        self,
        session_id: str,
        db_path: Optional[str] = None,
        restore_on_start: bool = True,
    ):
        """
        Initialize the bridge.

        Args:
            session_id: Unique session identifier
            db_path: Path to SQLite database (uses default if None)
            restore_on_start: Whether to restore from checkpoint on start
        """
        self._session_id = session_id
        self._db_path = db_path
        self._restore_on_start = restore_on_start

        # Create SessionStateManager via factory
        factory_kwargs: Dict[str, Any] = {"session_id": session_id}
        if db_path:
            from pathlib import Path

            factory_kwargs["db_path"] = Path(db_path)

        self._manager: SessionStateManager = SessionStateFactory.create_standalone(**factory_kwargs)

        # Write gate for deduplication
        from poc.session_state_demo.write_gate import WriteGate

        self._write_gate: WriteGate = WriteGate(self._manager)
        self._gate_enabled = True  # Can be toggled for comparison

        # State tracking
        self._turn_number = 0
        self._started = False
        self._stats = BridgeStats()
        self._recent_changes: List[StateChange] = []

    # =========================================================================
    # LIFECYCLE
    # =========================================================================

    def start(self) -> Tuple[bool, str]:
        """
        Start the session.

        Returns:
            Tuple of (success, message describing what happened)
        """
        if self._started:
            return False, "Session already started"

        result = self._manager.start(restore_if_exists=self._restore_on_start)
        self._started = True

        if result.restored:
            self._stats.restores_performed += 1
            # Restore turn number from meta or history
            self._sync_turn_number()
            return True, f"Restored session with {self._turn_number} turns"
        else:
            return True, "Started fresh session"

    def stop(self, checkpoint_before_stop: bool = True) -> Tuple[bool, str]:
        """
        Stop the session.

        Args:
            checkpoint_before_stop: Create checkpoint before stopping

        Returns:
            Tuple of (success, message)
        """
        if not self._started:
            return False, "Session not started"

        self._manager.stop(checkpoint_before_stop=checkpoint_before_stop)
        self._started = False
        return True, "Session stopped"

    def checkpoint(self) -> Tuple[bool, str, int]:
        """
        Create a checkpoint.

        Returns:
            Tuple of (success, message, bytes_saved)
        """
        if not self._started:
            return False, "Session not started", 0

        result = self._manager.checkpoint()
        if result.success:
            self._stats.checkpoints_created += 1
            return True, f"Checkpoint saved ({result.size_bytes:,} bytes)", result.size_bytes
        else:
            return False, f"Checkpoint failed: {result.error}", 0

    def crash_simulate(self) -> str:
        """
        Simulate a crash (stop without checkpoint).

        Returns:
            Message describing what happened
        """
        if self._started:
            self._manager.stop(checkpoint_before_stop=False)
            self._started = False
            return "Session crashed (no checkpoint saved)"
        return "Session was not running"

    def restore(self) -> Tuple[bool, str]:
        """
        Restore from last checkpoint after crash.

        Returns:
            Tuple of (success, message)
        """
        if self._started:
            return False, "Session already running - stop first"

        db_path = Path(self._db_path) if self._db_path else None
        self._manager = SessionStateFactory.create_standalone(
            session_id=self._session_id,
            db_path=db_path,
        )
        result = self._manager.start(restore_if_exists=True)
        self._started = True

        if result.restored:
            self._stats.restores_performed += 1
            self._sync_turn_number()
            return True, f"Restored session with {self._turn_number} turns"
        else:
            return False, "No checkpoint found to restore"

    def _sync_turn_number(self) -> None:
        """Sync turn number from history_active section."""
        try:
            history = self._manager.get_section("history_active")
            if hasattr(history, "get_all"):
                turns = history.get_all()
                self._turn_number = len(turns)
                self._stats.total_turns = self._turn_number
        except Exception:
            pass

    # =========================================================================
    # AUTOMATIC WRITES (Issue 1.2)
    # =========================================================================

    def record_user_turn(self, content: str) -> List[StateChange]:
        """
        Record a user turn (buffers for complete turn with assistant response).

        The actual write to history_active happens in record_assistant_turn()
        since the section requires both user and assistant messages together.

        Args:
            content: User message content

        Returns:
            List of state changes made (informational only)
        """
        changes: List[StateChange] = []
        self._turn_number += 1
        self._stats.user_turns += 1
        self._stats.total_turns += 1

        # Buffer the user message for later
        self._pending_user_message = content

        changes.append(
            StateChange(
                section="history_active",
                operation="buffer",
                description=f"User turn #{self._turn_number} buffered ({len(content)} chars)",
                bytes_delta=0,
                success=True,
                auto=True,
            )
        )

        self._recent_changes = changes
        return changes

    def record_assistant_turn(
        self,
        content: str,
        duration_ms: int,
        token_count: int = 0,
        had_tool_call: bool = False,
    ) -> List[StateChange]:
        """
        Record an assistant turn (writes complete turn to history_active).

        Writes to:
        - history_active: Complete turn (user + assistant)
        - telemetry: Turn timing

        Args:
            content: Assistant response content
            duration_ms: Response generation time in ms
            token_count: Tokens used for response
            had_tool_call: Whether response included tool calls

        Returns:
            List of state changes made
        """
        changes: List[StateChange] = []
        self._stats.assistant_turns += 1
        self._stats.total_latency_ms += duration_ms

        # Track latency SLI
        self._stats.turn_latencies_ms.append(duration_ms)
        if DEFAULT_SLO.evaluate(duration_ms) == "BREACH":
            self._stats.slo_violations += 1

        # Get buffered user message
        user_message = getattr(self, "_pending_user_message", "")
        self._pending_user_message = ""

        # Write complete turn to history_active
        result = self._manager.mutate(
            section="history_active",
            operation="append",
            data={
                "user_message": user_message,
                "assistant_response": content,
                "duration_ms": duration_ms,
            },
            estimated_bytes=len(user_message) + len(content) + 200,
        )

        changes.append(
            StateChange(
                section="history_active",
                operation="append",
                description=f"Assistant turn #{self._turn_number} ({len(content)} chars)",
                bytes_delta=result.bytes_delta,
                success=result.success,
                auto=True,
            )
        )

        # Write to telemetry
        result = self._manager.mutate(
            section="telemetry",
            operation="record_turn",
            data={
                "turn_number": self._turn_number,
                "duration_ms": duration_ms,
                "token_count": token_count,
                "had_error": False,
                "had_tool_call": had_tool_call,
            },
            estimated_bytes=50,
        )

        changes.append(
            StateChange(
                section="telemetry",
                operation="record_turn",
                description=f"Turn timing: {duration_ms}ms, {token_count} tokens",
                bytes_delta=result.bytes_delta,
                success=result.success,
                auto=True,
            )
        )

        self._recent_changes = changes
        return changes

    # =========================================================================
    # CONTEXT BUILDING (Issue 1.3)
    # =========================================================================

    def build_llm_context(self, max_history_turns: int = 10) -> Dict[str, Any]:
        """
        Build LLM context from session state.

        Reads from:
        - history_active: Recent conversation history
        - persona: User preferences and personality calibration
        - affective_now: Current emotional state

        Args:
            max_history_turns: Maximum turns to include in context

        Returns:
            Dict with:
            - system_prompt: Full system prompt
            - messages: Conversation history in LLM format
            - metadata: Additional context info
        """
        # Get history
        history = self._get_history_context(max_history_turns)

        # Get persona
        persona = self._get_persona_context()

        # Get emotional state
        emotional = self._get_emotional_context()

        # Build system prompt
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            persona_context=persona["description"],
            history_context=history["description"],
            emotional_context=emotional["description"],
        )

        # History already in message format from _get_history_context
        messages = history["turns"]

        return {
            "system_prompt": system_prompt,
            "messages": messages,
            "metadata": {
                "turn_number": self._turn_number,
                "persona_traits": persona.get("traits", {}),
                "emotional_state": emotional.get("state", {}),
            },
        }

    def _get_history_context(self, max_turns: int) -> Dict[str, Any]:
        """Get conversation history context."""
        try:
            history_section = self._manager.get_section("history_active")
            if hasattr(history_section, "get_recent"):
                turns = history_section.get_recent(max_turns)
                turn_data = []
                for turn in turns:
                    # Each Turn contains user_message and assistant_response
                    user_msg = getattr(turn, "user_message", "")
                    asst_msg = getattr(turn, "assistant_response", "")
                    if user_msg:
                        turn_data.append({"role": "user", "content": user_msg})
                    if asst_msg:
                        turn_data.append({"role": "assistant", "content": asst_msg})

                if turn_data:
                    description = f"Previous conversation ({len(turns)} turns in context)"
                else:
                    description = "This is the start of a new conversation."

                return {
                    "turns": turn_data,
                    "description": description,
                }
        except Exception as e:
            # Log the error instead of silently failing
            import logging

            logging.getLogger(__name__).warning(f"Failed to get history context: {e}")

        return {
            "turns": [],
            "description": "This is the start of a new conversation.",
        }

    def _get_persona_context(self) -> Dict[str, Any]:
        """Get persona context."""
        try:
            persona_section = self._manager.get_section("persona")
            traits = {}
            description_parts = []

            # Get personality traits if available
            if hasattr(persona_section, "get_personality"):
                personality = persona_section.get_personality()
                if hasattr(personality, "warmth"):
                    traits["warmth"] = personality.warmth
                if hasattr(personality, "formality"):
                    traits["formality"] = personality.formality
                if hasattr(personality, "verbosity"):
                    traits["verbosity"] = personality.verbosity

            # Get custom traits
            if hasattr(persona_section, "_traits"):
                for name, value in persona_section._traits.items():
                    traits[name] = value
                    description_parts.append(f"{name}: {value}")

            if description_parts:
                description = "Known user preferences:\n- " + "\n- ".join(description_parts)
            else:
                description = "No specific user preferences learned yet."

            return {
                "traits": traits,
                "description": description,
            }
        except Exception:
            pass

        return {
            "traits": {},
            "description": "No specific user preferences learned yet.",
        }

    def _get_emotional_context(self) -> Dict[str, Any]:
        """Get emotional state context."""
        try:
            affective = self._manager.get_section("affective_now")
            state = {}
            description = "Neutral conversational tone."

            if hasattr(affective, "_dominant_emotion"):
                emotion = affective._dominant_emotion
                intensity = getattr(affective, "_emotion_intensity", 0.5)
                if emotion and emotion != "neutral":
                    state["emotion"] = emotion
                    state["intensity"] = intensity
                    description = (
                        f"Current emotional context: {emotion} (intensity: {intensity:.1f})"
                    )

            if hasattr(affective, "_empathy_needed") and affective._empathy_needed:
                state["empathy_needed"] = True
                description += "\nThe user may need empathy or support."

            return {
                "state": state,
                "description": description,
            }
        except Exception:
            pass

        return {
            "state": {},
            "description": "Neutral conversational tone.",
        }

    def get_history_messages(self, max_turns: int = 20) -> List[Dict[str, str]]:
        """
        Get conversation history in LLM message format.

        Args:
            max_turns: Maximum turns to retrieve

        Returns:
            List of {"role": "user/assistant", "content": "..."}
        """
        return self._get_history_context(max_turns)["turns"]

    # =========================================================================
    # TOOL EXECUTION (with Write Gate)
    # =========================================================================

    def execute_tool_calls(self, tool_calls: List[Dict[str, Any]]) -> List[StateChange]:
        """
        Execute LLM tool calls to update session state.

        Uses WriteGate to prevent redundant writes (duplicates, spam).

        Args:
            tool_calls: List of {"name": "tool_name", "args": {...}}

        Returns:
            List of state changes made (including rejections)
        """
        changes: List[StateChange] = []

        for call in tool_calls:
            name = call.get("name", "")
            args = call.get("args", {})

            change = self._execute_single_tool(name, args)
            if change:
                changes.append(change)
                if change.success:
                    self._stats.tool_calls_executed += 1
                else:
                    self._stats.tool_calls_rejected += 1

        # Invalidate gate cache after writes
        if self._gate_enabled:
            self._write_gate.invalidate_cache()

        self._recent_changes.extend(changes)
        return changes

    def _execute_single_tool(self, name: str, args: Dict[str, Any]) -> Optional[StateChange]:
        """Execute a single tool call (with gate check)."""
        if name == "update_persona":
            return self._tool_update_persona(args)
        elif name == "update_emotion":
            return self._tool_update_emotion(args)
        elif name == "add_belief":
            return self._tool_add_belief(args)
        else:
            return StateChange(
                section="unknown",
                operation=name,
                description=f"Unknown tool: {name}",
                success=False,
                auto=False,
            )

    def _tool_update_persona(self, args: Dict[str, Any]) -> StateChange:
        """Update persona with learned preferences (gated)."""
        pref_name = args.get("preference_name", "")
        pref_value = args.get("preference_value", "")
        context = args.get("context", "")

        # Gate check
        if self._gate_enabled and pref_name and pref_value:
            decision = self._write_gate.check_persona(pref_name, pref_value, context)
            if not decision.allowed:
                self._stats.bytes_saved_by_gate += len(pref_name) + len(pref_value) + 50
                return StateChange(
                    section="persona",
                    operation="BLOCKED",
                    description=f"Duplicate: {decision.reason}",
                    bytes_delta=0,
                    success=False,
                    auto=False,
                )

        # Execute write
        for key, value in args.items():
            try:
                persona = self._manager.get_section("persona")
                if hasattr(persona, "add_trait"):
                    # Convert to float for trait storage
                    if isinstance(value, (int, float)):
                        persona.add_trait(key, float(value))
                    else:
                        # Store string as 1.0 with key as descriptor
                        persona.add_trait(f"{key}_{value}", 1.0)
            except Exception:
                pass

        description = ", ".join(f"{k}={v}" for k, v in args.items())
        return StateChange(
            section="persona",
            operation="add_trait",
            description=f"Learned: {description}",
            success=True,
            auto=False,
        )

    def _tool_update_emotion(self, args: Dict[str, Any]) -> StateChange:
        """Update emotional state (gated)."""
        emotion = args.get("emotion", "neutral")
        intensity = args.get("intensity", 0.5)

        # Gate check (emotions are more permissive)
        if self._gate_enabled:
            decision = self._write_gate.check_emotion(emotion, intensity)
            if not decision.allowed:
                return StateChange(
                    section="affective_now",
                    operation="BLOCKED",
                    description=f"Duplicate: {decision.reason}",
                    bytes_delta=0,
                    success=False,
                    auto=False,
                )

        try:
            affective = self._manager.get_section("affective_now")
            if hasattr(affective, "update_emotion"):
                affective.update_emotion(emotion, intensity)
        except Exception:
            pass

        return StateChange(
            section="affective_now",
            operation="update_emotion",
            description=f"Emotion: {emotion} ({intensity:.1f})",
            success=True,
            auto=False,
        )

    def _tool_add_belief(self, args: Dict[str, Any]) -> StateChange:
        """Add a learned belief/fact about user (gated)."""
        # Support both old format (fact, category) and new format (subject, predicate, object)
        subject = args.get("subject", "user")
        predicate = args.get("predicate", args.get("category", "general"))
        obj = args.get("object", args.get("fact", ""))
        confidence = args.get("confidence", 0.8)

        # Gate check
        fact_str = f"{subject} {predicate} {obj}"
        if self._gate_enabled and obj:
            decision = self._write_gate.check_belief(fact_str, predicate, confidence)
            if not decision.allowed:
                self._stats.bytes_saved_by_gate += len(fact_str) + 50
                return StateChange(
                    section="beliefs_active",
                    operation="BLOCKED",
                    description=f"Duplicate: {decision.reason}",
                    bytes_delta=0,
                    success=False,
                    auto=False,
                )

        result = self._manager.mutate(
            section="beliefs_active",
            operation="add_fact",
            data={
                "subject": subject,
                "predicate": predicate,
                "obj": obj,
                "confidence": confidence,
            },
            estimated_bytes=len(fact_str) + 50,
        )

        return StateChange(
            section="beliefs_active",
            operation="add_fact",
            description=f"Belief: {subject} {predicate} {obj}"[:60],
            bytes_delta=result.bytes_delta,
            success=result.success,
            auto=False,
        )

    # =========================================================================
    # SCOREBOARD WRITES
    # =========================================================================

    def update_scoreboard(
        self,
        topic: Optional[str] = None,
        qud: Optional[str] = None,
        referents: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> StateChange:
        """
        Update the scoreboard section with current discourse state.

        Args:
            topic: Current conversation topic (e.g., "accommodation_booking")
            qud: Question Under Discussion (e.g., "What hotel should we book?")
            referents: Dict of referent name -> {type, salience, last_mention}

        Returns:
            StateChange indicating what was updated
        """
        try:
            scoreboard = self._manager.get_section("scoreboard")
            updates = []

            if topic is not None:
                # Push topic or update existing
                if hasattr(scoreboard, "push_topic"):
                    # Check if topic already exists
                    existing_topics = (
                        scoreboard.list_topics() if hasattr(scoreboard, "list_topics") else []
                    )
                    topic_exists = any(t.name == topic for t in existing_topics)
                    if not topic_exists:
                        scoreboard.push_topic(topic, salience=0.8, is_primary=True)
                        updates.append(f"topic={topic}")

                # Also update user intent
                if hasattr(scoreboard, "set_user_intent"):
                    scoreboard.set_user_intent(topic, confidence=0.9)

            if qud is not None:
                # Push QUD (Question Under Discussion)
                if hasattr(scoreboard, "push_question"):
                    scoreboard.push_question(text=qud, asked_by="user")
                    updates.append(f"qud={qud[:30]}...")

            if referents is not None:
                # Update referents
                if hasattr(scoreboard, "add_referent"):
                    for name, data in referents.items():
                        scoreboard.add_referent(
                            text=name,
                            entity_id=data.get("entity_id", ""),
                            entity_type=data.get("type", ""),
                            salience=data.get("salience", 0.5),
                        )
                    updates.append(f"referents={len(referents)}")

            return StateChange(
                section="scoreboard",
                operation="update",
                description=", ".join(updates) if updates else "no changes",
                success=True,
                auto=True,
            )
        except Exception as e:
            return StateChange(
                section="scoreboard",
                operation="update",
                description=f"Error: {e}",
                success=False,
                auto=True,
            )

    def add_referent(
        self,
        name: str,
        ref_type: str,
        salience: float = 0.5,
        turn_mentioned: int = 0,
    ) -> None:
        """Add or update a referent in the scoreboard."""
        try:
            scoreboard = self._manager.get_section("scoreboard")
            if hasattr(scoreboard, "add_referent"):
                scoreboard.add_referent(
                    text=name,
                    entity_type=ref_type,
                    salience=salience,
                )
        except Exception:
            pass

    def decay_referent_salience(self, decay_factor: float = 0.9) -> None:
        """Decay salience of all referents (call each turn)."""
        try:
            scoreboard = self._manager.get_section("scoreboard")
            if hasattr(scoreboard, "decay_salience"):
                scoreboard.decay_salience()
        except Exception:
            pass

    # =========================================================================
    # CLARIFICATIONS WRITES
    # =========================================================================

    def add_clarification_gap(
        self,
        gap_type: str,
        question: str,
        turn_asked: int,
        confidence: float = 0.8,
    ) -> StateChange:
        """
        Add a pending clarification gap.

        Args:
            gap_type: Type of missing info (e.g., "date", "location", "budget")
            question: Natural language question to ask user
            turn_asked: Turn number when gap was detected
            confidence: Confidence that this info is needed (0-1)

        Returns:
            StateChange indicating result
        """
        try:
            clarifications = self._manager.get_section("clarifications")

            # Use proper ClarificationsSection API
            if hasattr(clarifications, "request"):
                # Check if we already have this gap type pending
                existing = (
                    clarifications.list_pending() if hasattr(clarifications, "list_pending") else []
                )
                gap_exists = any(c.related_intent == gap_type for c in existing)
                if not gap_exists:
                    clarifications.request(
                        agent_id="concierge",
                        question=question,
                        related_intent=gap_type,  # Use intent field to track gap type
                        blocking=True,
                    )

            return StateChange(
                section="clarifications",
                operation="add_gap",
                description=f"Gap: {gap_type} - {question[:30]}...",
                success=True,
                auto=True,
            )
        except Exception as e:
            return StateChange(
                section="clarifications",
                operation="add_gap",
                description=f"Error: {e}",
                success=False,
                auto=True,
            )

    def resolve_clarification_gap(self, gap_type: str) -> StateChange:
        """
        Mark a clarification gap as resolved.

        Args:
            gap_type: Type of gap that was answered

        Returns:
            StateChange indicating result
        """
        try:
            clarifications = self._manager.get_section("clarifications")

            # Find and answer the clarification by gap type (stored in related_intent)
            if hasattr(clarifications, "list_pending") and hasattr(clarifications, "answer"):
                pending = clarifications.list_pending()
                for c in pending:
                    if c.related_intent == gap_type:
                        clarifications.answer(
                            clarification_id=c.id,
                            answer=f"Resolved: {gap_type}",
                        )
                        break

            return StateChange(
                section="clarifications",
                operation="resolve_gap",
                description=f"Resolved: {gap_type}",
                success=True,
                auto=True,
            )
        except Exception as e:
            return StateChange(
                section="clarifications",
                operation="resolve_gap",
                description=f"Error: {e}",
                success=False,
                auto=True,
            )

    def clear_all_gaps(self) -> None:
        """Clear all pending clarification gaps."""
        try:
            clarifications = self._manager.get_section("clarifications")
            if hasattr(clarifications, "list_pending") and hasattr(clarifications, "cancel"):
                pending = clarifications.list_pending()
                for c in pending:
                    clarifications.cancel(c.id)
        except Exception:
            pass

    # =========================================================================
    # NARRATIVE WRITES
    # =========================================================================

    def update_narrative(
        self,
        phase: Optional[str] = None,
        thread: Optional[str] = None,
    ) -> StateChange:
        """
        Update narrative tracking.

        Args:
            phase: Current conversation phase (setup, booking, execution, crisis, resolution)
            thread: Active conversation thread description

        Returns:
            StateChange indicating result
        """
        try:
            narrative = self._manager.get_section("narrative_active")
            updates = []

            if thread is not None:
                # Create or switch to thread
                if hasattr(narrative, "create_thread"):
                    # Check if thread exists
                    primary = (
                        narrative._primary_thread if hasattr(narrative, "_primary_thread") else None
                    )
                    if primary is None or primary.title != thread:
                        narrative.create_thread(title=thread, goal=thread, auto_switch=True)
                        updates.append(f"thread={thread[:20]}...")

            if phase is not None:
                # Phase is tracked via narrative arc position
                # Map phase names to arc position
                if hasattr(narrative, "_arc"):
                    arc = narrative._arc
                    # Update arc progress based on phase
                    if phase == "setup":
                        arc._progress = 0.1
                    elif phase == "booking":
                        arc._progress = 0.3
                    elif phase == "execution":
                        arc._progress = 0.6
                    elif phase == "crisis":
                        arc._progress = 0.8
                    elif phase == "resolution":
                        arc._progress = 1.0
                    updates.append(f"phase={phase}")

            return StateChange(
                section="narrative_active",
                operation="update",
                description=", ".join(updates) if updates else "no changes",
                success=True,
                auto=True,
            )
        except Exception as e:
            return StateChange(
                section="narrative_active",
                operation="update",
                description=f"Error: {e}",
                success=False,
                auto=True,
            )

    # =========================================================================
    # WARM TIER: BELIEFS_HISTORY (Eviction from HOT)
    # =========================================================================

    def demote_beliefs_to_history(self, count: int = 5) -> StateChange:
        """
        Demote oldest beliefs from beliefs_active to beliefs_history.

        Called when beliefs_active is at capacity or periodically to maintain
        the HOT/WARM tier separation.

        Args:
            count: Number of beliefs to demote (default 5)

        Returns:
            StateChange indicating result
        """
        try:
            beliefs_active = self._manager.get_section("beliefs_active")
            beliefs_history = self._manager.get_section("beliefs_history")

            demoted = []

            # Get facts to demote from beliefs_active
            if hasattr(beliefs_active, "demote_facts"):
                facts = beliefs_active.demote_facts(count)
                # Convert to dict format for beliefs_history
                for fact in facts:
                    demoted.append(
                        {
                            "id": getattr(fact, "id", ""),
                            "subject": getattr(fact, "subject", ""),
                            "predicate": getattr(fact, "predicate", ""),
                            "object": getattr(fact, "object", ""),
                            "confidence": getattr(fact, "confidence", 1.0),
                            "source": getattr(fact, "source", ""),
                            "timestamp_ms": getattr(fact, "timestamp_ms", 0),
                        }
                    )
            elif hasattr(beliefs_active, "get_demotable_facts"):
                facts = beliefs_active.get_demotable_facts(count)
                for fact in facts:
                    beliefs_active.remove_fact(fact.id)
                    demoted.append(
                        {
                            "id": fact.id,
                            "subject": fact.subject,
                            "predicate": fact.predicate,
                            "object": fact.object,
                            "confidence": fact.confidence,
                        }
                    )

            # Accept into beliefs_history
            if demoted and hasattr(beliefs_history, "accept_demoted"):
                beliefs_history.accept_demoted(demoted, turn=self._turn_number)

            return StateChange(
                section="beliefs_history",
                operation="accept_demoted",
                description=f"Demoted {len(demoted)} beliefs from HOT to WARM",
                success=True,
                auto=True,
            )
        except Exception as e:
            return StateChange(
                section="beliefs_history",
                operation="accept_demoted",
                description=f"Error: {e}",
                success=False,
                auto=True,
            )

    def check_beliefs_capacity(self) -> bool:
        """
        Check if beliefs_active needs eviction.

        Returns:
            True if eviction is recommended
        """
        try:
            beliefs_active = self._manager.get_section("beliefs_active")
            if hasattr(beliefs_active, "get_size_bytes") and hasattr(
                beliefs_active, "BUDGET_BYTES"
            ):
                utilization = beliefs_active.get_size_bytes() / beliefs_active.BUDGET_BYTES
                return utilization > 0.8  # Trigger at 80% capacity
            return False
        except Exception:
            return False

    # =========================================================================
    # WARM TIER: HISTORY_RECENT (Overflow from history_active)
    # =========================================================================

    def overflow_history_to_recent(self) -> StateChange:
        """
        Move older turns from history_active to history_recent with compression.

        Called when history_active exceeds its turn limit (10 turns).
        Converts full turns to CompressedTurn format.

        Returns:
            StateChange indicating result
        """
        try:
            history_active = self._manager.get_section("history_active")
            history_recent = self._manager.get_section("history_recent")

            compressed_count = 0

            # Check if we have more than 10 turns in history_active
            if hasattr(history_active, "get_all"):
                turns = history_active.get_all()
                if len(turns) > 10:
                    # Get turns to compress (oldest ones beyond 10)
                    overflow_turns = turns[:-10]  # Keep last 10

                    for turn in overflow_turns:
                        # Extract key info for compression
                        user_msg = getattr(turn, "user_message", "")
                        asst_msg = getattr(turn, "assistant_response", "")

                        # Create compressed turn data
                        compressed_data = {
                            "turn_id": getattr(turn, "id", str(self._turn_number)),
                            "turn_number": getattr(turn, "turn_number", 0),
                            "entities": self._extract_entities(user_msg + " " + asst_msg),
                            "intents": [getattr(turn, "intent", "unknown")],
                            "key_phrases": self._extract_key_phrases(user_msg),
                            "emotion": getattr(turn, "emotion", ""),
                            "user_tokens": len(user_msg.split()),
                            "response_tokens": len(asst_msg.split()),
                        }

                        # Add to history_recent
                        if hasattr(history_recent, "add_compressed_turn"):
                            from k1.sessionstate.sections.history_recent import CompressedTurn

                            ct = CompressedTurn(
                                turn_id=compressed_data["turn_id"],
                                turn_number=compressed_data["turn_number"],
                                entities=compressed_data["entities"],
                                intents=compressed_data["intents"],
                                key_phrases=compressed_data["key_phrases"],
                                emotion=compressed_data["emotion"],
                                user_tokens=compressed_data["user_tokens"],
                                response_tokens=compressed_data["response_tokens"],
                            )
                            history_recent.add_compressed_turn(ct)
                            compressed_count += 1

                        # Remove from history_active
                        if hasattr(history_active, "remove_turn"):
                            history_active.remove_turn(turn.id)

            return StateChange(
                section="history_recent",
                operation="compress",
                description=f"Compressed {compressed_count} turns from HOT to WARM",
                success=True,
                auto=True,
            )
        except Exception as e:
            return StateChange(
                section="history_recent",
                operation="compress",
                description=f"Error: {e}",
                success=False,
                auto=True,
            )

    def _extract_entities(self, text: str) -> List[str]:
        """Extract entity mentions from text (simple implementation)."""
        # Simple capitalized word extraction as entities
        import re

        words = re.findall(r"\b[A-Z][a-z]+\b", text)
        return list(set(words))[:10]

    def _extract_key_phrases(self, text: str) -> List[str]:
        """Extract key phrases from text (simple implementation)."""
        # Simple extraction of short phrases
        words = text.split()
        if len(words) <= 5:
            return [text]
        # Take first few words and any quoted content
        import re

        quoted = re.findall(r'"([^"]+)"', text)
        return quoted[:3] if quoted else words[:5]

    def check_history_overflow(self) -> bool:
        """
        Check if history_active needs overflow to history_recent.

        Returns:
            True if overflow is needed
        """
        try:
            history_active = self._manager.get_section("history_active")
            if hasattr(history_active, "get_all"):
                turns = history_active.get_all()
                return len(turns) > 10
            return False
        except Exception:
            return False

    def set_gate_enabled(self, enabled: bool) -> None:
        """Enable or disable the write gate."""
        self._gate_enabled = enabled

    def get_gate_stats(self) -> Dict[str, Any]:
        """Get write gate statistics."""
        gate_stats = self._write_gate.get_stats()
        return {
            "total_checks": gate_stats.total_checks,
            "accepted": gate_stats.accepted,
            "rejected": gate_stats.rejected,
            "upgraded": gate_stats.upgraded,
            "bytes_saved": gate_stats.bytes_saved,
            "rejection_rate": f"{gate_stats.rejection_rate:.1%}",
        }

    # =========================================================================
    # INSPECTION
    # =========================================================================

    def get_snapshot(self) -> Dict[str, Any]:
        """Get current session state snapshot."""
        snapshot = self._manager.get_snapshot()
        return {
            "session_id": self._session_id,
            "turn_number": self._turn_number,
            "is_running": snapshot.is_running,
            "total_size_bytes": snapshot.total_size_bytes,
            "hot_utilization_pct": snapshot.hot_utilization_pct,
            "warm_utilization_pct": snapshot.warm_utilization_pct,
            "pressure": snapshot.pressure.value,
            "sections": {
                name: {
                    "size_bytes": info.size_bytes,
                    "utilization_pct": info.utilization_pct,
                }
                for name, info in snapshot.sections.items()
            },
        }

    def get_stats(self) -> BridgeStats:
        """Get session statistics."""
        return self._stats

    def get_latency_sli(self) -> Dict[str, Any]:
        """
        Get latency SLI metrics against SLO targets.

        Returns:
            Dict with percentiles, SLO targets, and breach info
        """
        latencies = self._stats.turn_latencies_ms
        if not latencies:
            return {
                "turn_count": 0,
                "p50_ms": 0,
                "p95_ms": 0,
                "p99_ms": 0,
                "max_ms": 0,
                "avg_ms": 0,
                "slo_p50_target_ms": DEFAULT_SLO.p50_target_ms,
                "slo_p95_target_ms": DEFAULT_SLO.p95_target_ms,
                "slo_p99_target_ms": DEFAULT_SLO.p99_target_ms,
                "slo_violations": 0,
                "slo_compliance_pct": 100.0,
            }

        sorted_latencies = sorted(latencies)
        n = len(sorted_latencies)

        def percentile(p: float) -> int:
            idx = int(n * p / 100)
            return sorted_latencies[min(idx, n - 1)]

        violations = self._stats.slo_violations
        compliance = ((n - violations) / n * 100) if n > 0 else 100.0

        return {
            "turn_count": n,
            "p50_ms": percentile(50),
            "p95_ms": percentile(95),
            "p99_ms": percentile(99),
            "max_ms": max(sorted_latencies),
            "min_ms": min(sorted_latencies),
            "avg_ms": sum(latencies) // n,
            "slo_p50_target_ms": DEFAULT_SLO.p50_target_ms,
            "slo_p95_target_ms": DEFAULT_SLO.p95_target_ms,
            "slo_p99_target_ms": DEFAULT_SLO.p99_target_ms,
            "slo_max_ms": DEFAULT_SLO.max_acceptable_ms,
            "slo_violations": violations,
            "slo_compliance_pct": round(compliance, 1),
        }

    def get_recent_changes(self) -> List[StateChange]:
        """Get list of recent state changes."""
        return self._recent_changes.copy()

    def get_section_data(self, section: str) -> Dict[str, Any]:
        """Get data from a specific section for inspection."""
        try:
            sec = self._manager.get_section(section)

            if section == "beliefs_active":
                data: Dict[str, Any] = {"beliefs": {}}
                if hasattr(sec, "list_facts"):
                    facts = sec.list_facts()
                    for fact in facts[:15]:  # Limit to 15 facts
                        subject = getattr(fact, "subject", "unknown")
                        predicate = getattr(fact, "predicate", "is")
                        obj = getattr(fact, "object", getattr(fact, "obj", ""))
                        if subject not in data["beliefs"]:
                            data["beliefs"][subject] = {}
                        data["beliefs"][subject][predicate] = obj
                elif hasattr(sec, "get_all_facts"):
                    facts = sec.get_all_facts()
                    for fact in facts[:15]:  # Limit to 15 facts
                        subject = getattr(fact, "subject", "unknown")
                        predicate = getattr(fact, "predicate", "is")
                        obj = getattr(fact, "object", getattr(fact, "obj", ""))
                        if subject not in data["beliefs"]:
                            data["beliefs"][subject] = {}
                        data["beliefs"][subject][predicate] = obj
                elif hasattr(sec, "_facts"):
                    # Fallback to internal storage
                    for fact in list(sec._facts.values())[:15]:
                        subject = getattr(fact, "subject", "unknown")
                        predicate = getattr(fact, "predicate", "is")
                        obj = getattr(fact, "object", getattr(fact, "obj", ""))
                        if subject not in data["beliefs"]:
                            data["beliefs"][subject] = {}
                        data["beliefs"][subject][predicate] = obj
                return data

            elif section == "history_active":
                if hasattr(sec, "get_all"):
                    turns = sec.get_all()
                    return {
                        "turn_count": len(turns),
                        "turns": [
                            {
                                "user": getattr(t, "user_message", "")[:80] + "...",
                                "assistant": getattr(t, "assistant_response", "")[:80] + "...",
                            }
                            for t in turns[-5:]  # Last 5 turns
                        ],
                    }

            elif section == "persona":
                data: Dict[str, Any] = {}
                if hasattr(sec, "_traits"):
                    data["traits"] = dict(sec._traits)
                if hasattr(sec, "get_personality"):
                    p = sec.get_personality()
                    data["personality"] = {
                        "warmth": getattr(p, "warmth", 0.5),
                        "formality": getattr(p, "formality", 0.5),
                        "verbosity": getattr(p, "verbosity", 0.5),
                    }
                return data

            elif section == "affective_now":
                if hasattr(sec, "_dominant_emotion"):
                    return {
                        "emotion": sec._dominant_emotion,
                        "intensity": getattr(sec, "_emotion_intensity", 0.5),
                        "empathy_needed": getattr(sec, "_empathy_needed", False),
                    }

            elif section == "telemetry":
                data = {}
                if hasattr(sec, "_turn_count"):
                    data["turn_count"] = sec._turn_count
                if hasattr(sec, "_tool_call_count"):
                    data["tool_call_count"] = sec._tool_call_count
                if hasattr(sec, "_total_latency_ms"):
                    data["total_latency_ms"] = sec._total_latency_ms
                if hasattr(sec, "_error_count"):
                    data["error_count"] = sec._error_count
                if hasattr(sec, "_session_start_ms"):
                    data["session_start_ms"] = sec._session_start_ms
                return data if data else {"turn_count": 0, "tool_call_count": 0}

            elif section == "beliefs_history":
                data = {"facts": [], "count": 0}
                if hasattr(sec, "_facts"):
                    data["count"] = len(sec._facts)
                    # Return summary of archived facts
                    for archived in list(sec._facts)[:10]:
                        fact = getattr(archived, "fact", archived)
                        data["facts"].append(
                            {
                                "subject": getattr(fact, "subject", ""),
                                "predicate": getattr(fact, "predicate", ""),
                                "object": getattr(fact, "object", ""),
                                "access_count": getattr(archived, "access_count", 0),
                            }
                        )
                return data

            elif section == "history_recent":
                data = {"compressed_turns": [], "summarized_turns": [], "session_summary": ""}
                if hasattr(sec, "_compressed_turns"):
                    for ct in list(sec._compressed_turns)[:10]:
                        data["compressed_turns"].append(
                            {
                                "turn_number": getattr(ct, "turn_number", 0),
                                "entities": getattr(ct, "entities", []),
                                "intents": getattr(ct, "intents", []),
                                "key_phrases": getattr(ct, "key_phrases", []),
                            }
                        )
                if hasattr(sec, "_summarized_turns"):
                    for st in list(sec._summarized_turns)[:5]:
                        data["summarized_turns"].append(
                            {
                                "turn_number": getattr(st, "turn_number", 0),
                                "summary": getattr(st, "summary", ""),
                            }
                        )
                if hasattr(sec, "_session_summary"):
                    data["session_summary"] = sec._session_summary
                return data

            elif section == "scoreboard":
                data: Dict[str, Any] = {}
                # Get topic from topic stack
                if hasattr(sec, "get_primary_topic"):
                    topic = sec.get_primary_topic()
                    if topic:
                        data["topic"] = topic.name
                elif hasattr(sec, "_topic_stack") and sec._topic_stack:
                    data["topic"] = sec._topic_stack[-1].name
                # Get QUD from qud stack
                if hasattr(sec, "peek_question"):
                    qud = sec.peek_question()
                    if qud:
                        data["qud"] = qud.text
                elif hasattr(sec, "_qud_stack") and sec._qud_stack:
                    data["qud"] = sec._qud_stack[-1].text
                # Get intent
                if hasattr(sec, "get_user_intent"):
                    intent, conf = sec.get_user_intent()
                    if intent:
                        data["last_intent"] = intent
                        data["intent_confidence"] = conf
                # Get referents
                if hasattr(sec, "_referents"):
                    data["referents"] = {
                        k: {
                            "salience": getattr(v, "salience", 0.5),
                            "type": getattr(v, "entity_type", ""),
                        }
                        for k, v in list(sec._referents.items())[:5]
                    }
                return data if data else {"topic": None, "qud": None, "referents": {}}

            elif section == "clarifications":
                data = {"gaps": [], "is_blocked": False, "pending_count": 0}
                if hasattr(sec, "list_pending"):
                    pending = sec.list_pending()
                    data["pending_count"] = len(pending)
                    for clar in list(pending)[:5]:
                        data["gaps"].append(
                            {
                                "type": getattr(clar, "related_intent", "unknown"),
                                "question": getattr(clar, "question", ""),
                                "agent": getattr(clar, "agent_id", ""),
                                "blocking": getattr(clar, "is_blocking", False),
                            }
                        )
                elif hasattr(sec, "_pending"):
                    data["pending_count"] = len(sec._pending)
                    for cid, clar in list(sec._pending.items())[:5]:
                        data["gaps"].append(
                            {
                                "type": getattr(clar, "related_intent", "unknown"),
                                "question": getattr(clar, "question", ""),
                            }
                        )
                if hasattr(sec, "_is_blocked"):
                    data["is_blocked"] = sec._is_blocked
                return data

            elif section == "narrative_active":
                data: Dict[str, Any] = {}
                # Get primary thread
                if hasattr(sec, "_primary_thread") and sec._primary_thread:
                    thread = sec._primary_thread
                    data["thread"] = thread.title
                    data["thread_goal"] = getattr(thread, "goal", "")
                    data["thread_state"] = getattr(thread, "state", 0)
                # Get arc position
                if hasattr(sec, "_arc"):
                    arc = sec._arc
                    if hasattr(arc, "_position"):
                        positions = ["exposition", "rising_action", "climax", "resolution"]
                        data["phase"] = (
                            positions[arc._position]
                            if arc._position < len(positions)
                            else "unknown"
                        )
                    if hasattr(arc, "_progress"):
                        data["progress"] = arc._progress
                # Get paused thread count
                if hasattr(sec, "_paused_threads"):
                    data["paused_threads"] = len(sec._paused_threads)
                return data if data else {"phase": "unknown", "thread": ""}

            elif section == "meta":
                data = {}
                if hasattr(sec, "_session_id"):
                    data["session_id"] = sec._session_id
                if hasattr(sec, "_turn_count"):
                    data["turn_count"] = sec._turn_count
                if hasattr(sec, "_started_at"):
                    data["started_at"] = str(sec._started_at)
                return data

            return {"raw": str(sec)[:200]}
        except Exception as e:
            return {"error": str(e)}

    @property
    def session_id(self) -> str:
        """Get session ID."""
        return self._session_id

    @property
    def turn_number(self) -> int:
        """Get current turn number."""
        return self._turn_number

    @property
    def is_running(self) -> bool:
        """Check if session is running."""
        return self._started
