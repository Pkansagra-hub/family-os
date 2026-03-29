"""
Concierge FSM
=============

Main state machine for the Concierge conversation loop.

States: LISTENING -> ACKING -> CLARIFYING? -> DISPATCHING -> EXECUTING -> DELIVERING
                        |                          ^
                        v (gaps found)             |
                   CLARIFYING -----> (user responds) -> ACKING

Reference: k1_cognitive_architecture_skeleton.mmd L1_CONCIERGE
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from poc.session_state_demo.concierge.classifier import IntentClassifier

# Fix 2: FSM Constraint Enforcement
from poc.session_state_demo.concierge.constraints import get_enforcer
from poc.session_state_demo.concierge.context_resolver import create_context_resolver
from poc.session_state_demo.concierge.gap_detector import GapDetector
from poc.session_state_demo.concierge.llm_gap_detector import (
    HybridGapDetector,
    LLMGapDetector,
)
from poc.session_state_demo.concierge.router import ComplexityRouter, RoutingDecision
from poc.session_state_demo.concierge.states import (
    ClassificationResult,
    ConciergeState,
    FSMStats,
    Gap,
    TurnResult,
    is_valid_transition,
)

# Tool bundle validation
try:
    from poc.session_state_demo.anniversary_demo.tools.validator import (
        ValidationResult,
        validate_tool_bundle,
    )

    HAS_VALIDATOR = True
except ImportError:
    HAS_VALIDATOR = False

if TYPE_CHECKING:
    from poc.session_state_demo.bridge import SessionLLMBridge

logger = logging.getLogger(__name__)


# =============================================================================
# FSM OBSERVER FOR DEBUGGING/DISPLAY
# =============================================================================


@dataclass
class FSMEvent:
    """Event emitted by FSM for observation."""

    event_type: str  # "llm_call", "llm_response", "gap_detection", "tool_call", etc.
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp_ms: int = 0


class FSMObserver:
    """Observer interface for FSM events."""

    def on_event(self, event: FSMEvent) -> None:
        """Called when an FSM event occurs."""
        pass


# =============================================================================
# DYNAMIC PROMPT BUILDER (shared with runner.py)
# =============================================================================
# Import from runner to avoid duplication
# We'll define a local version that FSM can use independently


class DynamicPromptBuilder:
    """
    Builds dynamic system prompts by injecting context from all 12 SessionState sections.
    """

    BASE_IDENTITY = """You are the FamilyOS Concierge - an intelligent family assistant.
You have READ/WRITE access to the family's SessionState via tools.
You LEARN information through conversation - never assume or pre-fill details."""

    RESPONSE_STYLE = """
CRITICAL TOOL CALLING RULES:
1. acknowledge() MUST be called FIRST before ANY effectful tool
2. Effectful tools: book_*, plan_route, schedule_*, send_*, create_*, start_*, add_belief, update_*
3. If acknowledge(next_tool="X"), you MUST call X immediately after

VALID:
  acknowledge(next_tool="search_restaurants") + search_restaurants(...)
  acknowledge(next_tool="none")  # text-only response

INVALID (WILL FAIL):
  plan_route(...) without acknowledge first -> REJECTED
  book_restaurant(...) without acknowledge first -> REJECTED

CORE PRINCIPLE - ASK, DON'T ASSUME:
- Start each conversation knowing NOTHING about the specific request
- Learn through conversation: who, what, when, where, budget, constraints
- NEVER assume budget, dates, locations, party size, or preferences
- If critical info is missing, ASK before proceeding

RESPONSE STYLE:
- Be conversational and natural - SHORT when appropriate, DETAILED when needed
- Greetings: 1-2 sentences max
- Confirmations: Brief acknowledgment + next step
- NEVER repeat back everything the user said
- Reference stored facts naturally ("I remember you mentioned...")
- When something is already booked, SAY SO - don't offer to book it again
- ALWAYS ask about dietary restrictions/allergies before booking food"""

    SPAWNABLE_AGENTS = """
SPAWNABLE SUB-AGENTS:
- SearchAgent: For searching (READ-ONLY access)
- BookingAgent: For reservations (READ-ONLY access, confirms with you)
- MonitorAgent: For background monitoring"""

    def __init__(
        self,
        bridge: "SessionLLMBridge",
        tool_registry: Optional[Any] = None,
        resolved_refs: Optional[Dict[str, Any]] = None,
        plan_controller: Optional[Any] = None,
    ):
        self._bridge = bridge
        self._tool_registry = tool_registry
        self._resolved_refs = resolved_refs or {}
        self._plan_controller = plan_controller

    def build_prompt(self) -> str:
        """Build complete dynamic system prompt."""
        sections = [
            self.BASE_IDENTITY,
            self._build_plan_context(),  # AUTHORITATIVE PLAN STATE first
            self._build_context_section(),
            self._build_resolved_refs_section(),
            self._build_tools_section(),
            self.SPAWNABLE_AGENTS,
            self.RESPONSE_STYLE,
        ]
        return "\n\n".join(filter(None, sections))

    def _build_plan_context(self) -> str:
        """Build AUTHORITATIVE plan context from PlanController."""
        if not self._plan_controller:
            return ""
        try:
            return self._plan_controller.get_prompt_context()
        except Exception:
            return ""

    def _build_resolved_refs_section(self) -> str:
        """Build section for resolved references that should NOT be asked about."""
        if not self._resolved_refs:
            return ""

        lines = ["ALREADY RESOLVED (DO NOT ASK ABOUT THESE):"]
        for key, ref in self._resolved_refs.items():
            if hasattr(ref, "resolved"):
                lines.append(f"- {ref.original} = {ref.resolved} (LOCKED)")
            elif isinstance(ref, dict):
                lines.append(f"- {ref.get('original', key)} = {ref.get('resolved', '')} (LOCKED)")
            else:
                lines.append(f"- {key} = {ref} (LOCKED)")

        lines.append("")
        lines.append(
            "IMPORTANT: The above items are RESOLVED. Do NOT ask for clarification about them."
        )
        return "\n".join(lines)

    def _build_context_section(self) -> str:
        """Build context from SessionState sections."""
        parts = ["CURRENT SESSION CONTEXT:"]

        # Beliefs
        beliefs = self._get_section("beliefs_active", "beliefs")
        if beliefs:
            parts.append(f"\nKNOWN FACTS:\n{beliefs}")

        # Persona
        persona = self._get_section("persona", "traits")
        if persona:
            parts.append(f"\nUSER PREFERENCES:\n{persona}")

        # Scoreboard
        scoreboard = self._get_scoreboard()
        if scoreboard:
            parts.append(f"\nCURRENT FOCUS:\n{scoreboard}")

        # Emotional state
        emotional = self._get_emotional()
        if emotional:
            parts.append(f"\nEMOTIONAL STATE:\n{emotional}")

        # Clarifications
        clarifications = self._get_clarifications()
        if clarifications:
            parts.append(f"\nPENDING CLARIFICATIONS:\n{clarifications}")

        return "\n".join(parts)

    def _get_section(self, section_name: str, key: str) -> str:
        """Get section data."""
        try:
            data = self._bridge.get_section_data(section_name)
            if "error" in data:
                return ""

            content = data.get(key, data.get("raw", ""))
            if isinstance(content, dict):
                lines = []
                for k, v in list(content.items())[:10]:
                    if isinstance(v, dict):
                        for k2, v2 in v.items():
                            lines.append(f"- {k} {k2} {v2}")
                    else:
                        lines.append(f"- {k}: {v}")
                return "\n".join(lines)
            return str(content)[:500] if content else ""
        except Exception:
            return ""

    def _get_scoreboard(self) -> str:
        """Get scoreboard info."""
        try:
            data = self._bridge.get_section_data("scoreboard")
            if "error" in data or not data:
                return ""
            lines = []
            if "topic" in data:
                lines.append(f"- Current topic: {data['topic']}")
            if "qud" in data:
                lines.append(f"- Question: {data['qud']}")
            return "\n".join(lines)
        except Exception:
            return ""

    def _get_emotional(self) -> str:
        """Get emotional state."""
        try:
            data = self._bridge.get_section_data("affective_now")
            if "error" in data:
                return ""
            emotion = data.get("emotion", "neutral")
            intensity = data.get("intensity", 0.5)
            return f"- User emotion: {emotion} (intensity: {intensity:.1f})"
        except Exception:
            return ""

    def _get_clarifications(self) -> str:
        """Get pending clarifications."""
        try:
            data = self._bridge.get_section_data("clarifications")
            if "error" in data or not data:
                return ""
            gaps = data.get("gaps", [])
            lines = [
                f"- Missing: {g.get('type', 'unknown')} - {g.get('question', '')}" for g in gaps[:3]
            ]
            return "\n".join(lines)
        except Exception:
            return ""

    def _build_tools_section(self) -> str:
        """Build available tools section."""
        if not self._tool_registry:
            return ""

        lines = ["AVAILABLE TOOLS:"]
        try:
            schemas = self._tool_registry.get_all_schemas_for_llm()
            for tool in schemas[:20]:  # Limit display
                name = tool.get("function", {}).get("name", "unknown")
                desc = tool.get("function", {}).get("description", "")[:60]
                lines.append(f"- {name}: {desc}...")
        except Exception:
            pass

        return "\n".join(lines) if len(lines) > 1 else ""


@dataclass
class FSMContext:
    """Context maintained across FSM states."""

    # Current turn number
    turn_count: int = 0

    # Current classification
    classification: Optional[ClassificationResult] = None

    # Pending clarification
    pending_gap: Optional[Gap] = None
    clarification_count: int = 0
    max_clarifications: int = 2

    # Routing decision
    routing: Optional[RoutingDecision] = None

    # Execution results
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    tool_results: List[Dict[str, Any]] = field(default_factory=list)

    # Response building
    response: str = ""

    def reset(self) -> None:
        """Reset context for new turn."""
        self.classification = None
        self.routing = None
        self.tool_calls = []
        self.tool_results = []
        self.response = ""
        # Don't reset pending_gap, clarification_count, or turn_count - those persist


class ConciergeFSM:
    """
    Simplified Concierge FSM for the session state demo.

    Implements the core conversation loop:
    1. LISTENING: Wait for user input
    2. ACKING: Classify intent, detect gaps
    3. CLARIFYING: Ask for missing info (if needed)
    4. DISPATCHING: Route by complexity
    5. EXECUTING: Run tools / LLM
    6. DELIVERING: Return response

    Usage:
        fsm = ConciergeFSM(bridge, llm_client)

        # Process a turn
        result = await fsm.process_input("Plan a trip to Japan")

        if result.needs_clarification:
            # Show clarification question to user
            print(result.clarification_question)
        else:
            # Show response
            print(result.response)
    """

    def __init__(
        self,
        bridge: "SessionLLMBridge",
        llm_client: Any,
        on_state_change: Optional[Callable[[ConciergeState, ConciergeState], None]] = None,
        tool_registry: Optional[Any] = None,
        tool_executor: Optional[Any] = None,
        enable_llm_gap_detection: bool = True,
        observers: Optional[List[FSMObserver]] = None,
        plan_controller: Optional[Any] = None,
    ):
        """
        Initialize FSM.

        Args:
            bridge: SessionLLMBridge for state access
            llm_client: LLM client for completions
            on_state_change: Optional callback for state transitions
            tool_registry: Optional tool registry for LLM function calling
            tool_executor: Optional tool executor for running tools
            enable_llm_gap_detection: Use LLM for intelligent gap detection
            observers: Optional list of observers for FSM events
            plan_controller: Optional PlanController for authoritative plan state
        """
        self._bridge = bridge
        self._llm = llm_client
        self._on_state_change = on_state_change
        self._tool_registry = tool_registry
        self._tool_executor = tool_executor
        self._enable_llm_gap_detection = enable_llm_gap_detection
        self._observers: List[FSMObserver] = observers or []
        self._plan_controller = plan_controller  # Fix 1: Canonical Plan Object

        # Fix 2: FSM Constraint Enforcer
        self._constraint_enforcer = get_enforcer(strict_mode=False)

        # Initialize components
        self._classifier = IntentClassifier()
        self._gap_detector = GapDetector()
        self._router = ComplexityRouter()
        self._context_resolver = create_context_resolver(bridge)

        # LLM-powered gap detection (M7)
        if enable_llm_gap_detection:
            llm_gap_detector = LLMGapDetector(llm_client=llm_client, bridge=bridge)
            self._hybrid_gap_detector = HybridGapDetector(
                llm_detector=llm_gap_detector,
                heuristic_detector=self._gap_detector,
                llm_threshold=0.7,
            )
        else:
            self._hybrid_gap_detector = None

        # FSM state
        self._state = ConciergeState.LISTENING
        self._context = FSMContext()
        self._stats = FSMStats()

        # State history for debugging
        self._state_history: List[ConciergeState] = [ConciergeState.LISTENING]

    def set_plan_controller(self, plan_controller: Any) -> None:
        """Set the plan controller after initialization."""
        self._plan_controller = plan_controller

    # =========================================================================
    # OBSERVER METHODS
    # =========================================================================

    def add_observer(self, observer: FSMObserver) -> None:
        """Add an observer for FSM events."""
        self._observers.append(observer)

    def remove_observer(self, observer: FSMObserver) -> None:
        """Remove an observer."""
        if observer in self._observers:
            self._observers.remove(observer)

    def _emit_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Emit an event to all observers."""
        event = FSMEvent(
            event_type=event_type,
            data=data,
            timestamp_ms=int(time.time() * 1000),
        )
        for observer in self._observers:
            try:
                observer.on_event(event)
            except Exception as e:
                logger.warning(f"Observer error: {e}")

    @property
    def state(self) -> ConciergeState:
        """Current FSM state."""
        return self._state

    @property
    def stats(self) -> FSMStats:
        """FSM statistics."""
        return self._stats

    def get_stats_dict(self) -> Dict[str, Any]:
        """Get stats as dictionary."""
        return {
            "total_turns": self._stats.total_turns,
            "clarifications_triggered": self._stats.clarifications_triggered,
            "low_tier_count": self._stats.low_tier_count,
            "medium_tier_count": self._stats.medium_tier_count,
            "avg_classification_ms": round(self._stats.avg_classification_ms, 1),
            "state_transition_count": self._stats.state_transition_count,
        }

    # =========================================================================
    # STATE TRANSITIONS
    # =========================================================================

    def _transition(self, new_state: ConciergeState) -> None:
        """
        Transition to a new state.

        Args:
            new_state: Target state

        Raises:
            ValueError: If transition is invalid
        """
        if not is_valid_transition(self._state, new_state):
            raise ValueError(f"Invalid transition: {self._state.name} -> {new_state.name}")

        old_state = self._state
        self._state = new_state
        self._state_history.append(new_state)

        # Notify callback
        if self._on_state_change:
            self._on_state_change(old_state, new_state)

    # =========================================================================
    # MAIN PROCESSING
    # =========================================================================

    async def process_input(self, user_input: str) -> TurnResult:
        """
        Process user input through the FSM.

        This is the main entry point for each turn.

        Args:
            user_input: The user's message

        Returns:
            TurnResult with response and metadata
        """
        start_time = time.time()

        # Increment turn count
        self._context.turn_count += 1

        # Ensure FSM is in LISTENING state at start of each turn
        # This handles recovery from errors that left FSM in wrong state
        if self._state != ConciergeState.LISTENING:
            self._state = ConciergeState.LISTENING

        self._state_history = [self._state]

        # Are we expecting a clarification response?
        is_clarification = self._context.pending_gap is not None

        # Reset context for new turn (but keep pending_gap)
        self._context.reset()

        # LISTENING -> ACKING
        self._transition(ConciergeState.ACKING)

        # === RESOLVE TEMPORAL AND ENTITY REFERENCES FIRST ===
        # This prevents re-asking for "next Saturday" etc.
        session_context = self._get_session_context()
        context_resolution = self._context_resolver.resolve(
            user_input=user_input,
            turn_number=self._context.turn_count,
            scoreboard=session_context.get("scoreboard"),
            beliefs=session_context.get("beliefs", {}).get("beliefs", {}),
        )

        # Classify input
        classification_start = time.time()
        classification = self._classifier.classify(
            user_input,
            session_context=session_context,
            is_clarification_response=is_clarification,
        )
        classification_ms = int((time.time() - classification_start) * 1000)
        self._context.classification = classification

        # If this was a clarification response, clear pending gap
        if is_clarification:
            # Resolve gap in SessionState
            if self._context.pending_gap:
                self._bridge.resolve_clarification_gap(self._context.pending_gap.gap_type)
            self._context.pending_gap = None
            self._context.clarification_count = 0

        # Check for gaps requiring clarification
        # DISABLED: Gap detection now happens AFTER LLM decides what tool to call
        # The LLM is smart enough to ask for missing info if needed
        gaps = []  # Don't do upfront gap detection

        # DISABLED: Old filtering and LLM gap detection - not needed
        # The LLM handles missing info by asking directly

        # === PROCEED DIRECTLY TO EXECUTION ===
        # No clarification needed - proceed to execution
        # ACKING -> DISPATCHING
        self._transition(ConciergeState.DISPATCHING)

        # Route by complexity
        routing = self._router.route(classification)
        self._context.routing = routing

        # DISPATCHING -> EXECUTING
        self._transition(ConciergeState.EXECUTING)

        # Execute based on routing
        execution_start = time.time()
        if routing.custom_response:
            # Simple response (greeting)
            self._context.response = routing.custom_response
        else:
            # LLM execution
            await self._execute_llm(user_input, classification, routing)

        execution_ms = int((time.time() - execution_start) * 1000)

        # EXECUTING -> DELIVERING
        self._transition(ConciergeState.DELIVERING)

        # Build result
        result = TurnResult(
            final_state=self._state,
            response=self._context.response,
            needs_clarification=False,
            classification=classification,
            tier=routing.tier,
            tool_calls=self._context.tool_calls,
            tools_executed=len(self._context.tool_calls),
            tools_blocked=0,
            state_history=self._state_history.copy(),
            total_ms=int((time.time() - start_time) * 1000),
            classification_ms=classification_ms,
            execution_ms=execution_ms,
        )

        # DELIVERING -> LISTENING
        self._transition(ConciergeState.LISTENING)

        self._stats.record_turn(result)
        return result

    def _should_clarify(self) -> bool:
        """Check if we should ask for clarification."""
        # Don't clarify too many times in a row
        return self._context.clarification_count < self._context.max_clarifications

    def _get_session_context(self) -> Dict[str, Any]:
        """Get context from SessionState for classification and gap detection."""
        try:
            context = {
                "history": self._bridge.get_section_data("history_active"),
                "persona": self._bridge.get_section_data("persona"),
                "beliefs": self._bridge.get_section_data("beliefs_active"),
                "scoreboard": self._bridge.get_section_data("scoreboard"),
            }
            # Add resolved references from context resolver
            context["resolved_refs"] = self._context_resolver.get_all_resolved()
            return context
        except Exception:
            return {}

    # =========================================================================
    # EXECUTION
    # =========================================================================

    async def _execute_llm(
        self,
        user_input: str,
        classification: ClassificationResult,
        routing: RoutingDecision,
    ) -> None:
        """Execute LLM call with agentic tool loop.

        This implements a proper ReAct-style loop:
        1. Call LLM with user input
        2. If LLM returns tool calls, execute them
        3. Send tool results back to LLM
        4. Repeat until LLM returns final text response (no more tools)
        """
        MAX_TOOL_ITERATIONS = 10  # Safety limit to prevent infinite loops

        # Build DYNAMIC system prompt (not static!)
        # Pass resolved refs to prevent LLM from re-asking resolved info
        resolved_refs = self._context_resolver.get_all_resolved()
        prompt_builder = DynamicPromptBuilder(
            self._bridge,
            self._tool_registry,
            resolved_refs=resolved_refs,
            plan_controller=self._plan_controller,  # Fix 1: Canonical Plan
        )
        system_prompt = prompt_builder.build_prompt()

        # Get messages from bridge - use 25 turns to capture full conversation
        context = self._bridge.build_llm_context(max_history_turns=25)
        messages = context["messages"].copy()
        messages.append({"role": "user", "content": user_input})

        # Get tools from registry or fallback to basic tools
        if self._tool_registry:
            tools = self._tool_registry.get_all_schemas_for_llm()
        else:
            from poc.session_state_demo.tools import SESSIONSTATE_TOOLS

            tools = SESSIONSTATE_TOOLS

        # =====================================================================
        # AGENTIC TOOL LOOP - Keep calling LLM until task is complete
        # =====================================================================
        iteration = 0
        all_tool_calls = []  # Track all tools called across iterations
        final_content = ""

        while iteration < MAX_TOOL_ITERATIONS:
            iteration += 1

            # Emit LLM call event
            self._emit_event(
                "llm_call",
                {
                    "model": getattr(self._llm, "model", "gemini"),
                    "prompt_preview": system_prompt[:200] if system_prompt else "",
                    "message_count": len(messages),
                    "tool_count": len(tools) if tools else 0,
                    "requires_tools": routing.requires_tools,
                    "iteration": iteration,
                },
            )

            llm_start = time.time()

            # Call LLM
            if routing.requires_tools or iteration > 1:  # Always allow tools after first iteration
                response = await self._llm.complete_with_tools(
                    system_prompt=system_prompt,
                    messages=messages,
                    tools=tools,
                )
            else:
                try:
                    content = await self._llm.complete(
                        system_prompt=system_prompt,
                        messages=messages,
                    )
                    response = {"content": content, "tool_calls": []}
                except AttributeError:
                    response = await self._llm.complete_with_tools(
                        system_prompt=system_prompt,
                        messages=messages,
                        tools=[],
                    )

            llm_latency_ms = int((time.time() - llm_start) * 1000)

            # Get tool calls and content from response
            tool_calls = response.get("tool_calls", [])
            content = response.get("content", "")

            # Emit LLM response event
            self._emit_event(
                "llm_response",
                {
                    "latency_ms": llm_latency_ms,
                    "tool_calls": tool_calls,
                    "content_preview": content[:200] if content else "",
                    "tool_call_count": len(tool_calls),
                    "iteration": iteration,
                },
            )

            # If no tool calls, we're done - LLM gave final response
            if not tool_calls:
                final_content = content
                break

            # Track all tool calls
            all_tool_calls.extend(tool_calls)
            self._context.tool_calls = all_tool_calls

            # Tier-1 Validation (first iteration only)
            if iteration == 1 and HAS_VALIDATOR:
                validation = validate_tool_bundle(tool_calls, strict=False)
                if validation.errors:
                    for error in validation.errors:
                        logger.error(f"Tool validation error: {error}")
                        self._emit_event("validation_error", {"error": error, "severity": "error"})
                if validation.warnings:
                    for warning in validation.warnings:
                        logger.warning(f"Tool validation warning: {warning}")
                        self._emit_event(
                            "validation_warning", {"warning": warning, "severity": "warning"}
                        )

            # Execute tools and collect results
            tool_results = []
            for call in tool_calls:
                tool_name = call.get("name", "")
                tool_args = call.get("args", {})

                # Emit tool call event
                self._emit_event(
                    "tool_call",
                    {
                        "name": tool_name,
                        "args": tool_args,
                        "iteration": iteration,
                    },
                )

                # Execute tool
                result = None
                result_data = {}
                result_message = ""
                result_success = True

                if self._tool_executor:
                    result = self._tool_executor.execute(tool_name, tool_args)
                    result_success = result.success if hasattr(result, "success") else True
                    result_message = result.message if hasattr(result, "message") else ""
                    result_data = result.data if hasattr(result, "data") else {}

                    # Notify PlanController
                    if self._plan_controller:
                        self._plan_controller.on_tool_result(
                            tool_name=tool_name,
                            args=tool_args,
                            result=result_data,
                        )
                else:
                    # Fallback to bridge execution
                    self._bridge.execute_tool_calls([call])
                    result_message = f"{tool_name} executed"
                    result_data = {"status": "completed"}

                # Emit tool execution result
                self._emit_event(
                    "tool_execution_result",
                    {
                        "name": tool_name,
                        "success": result_success,
                        "message": result_message,
                        "data": result_data,
                        "iteration": iteration,
                    },
                )

                # Collect result for sending back to LLM
                tool_results.append(
                    {
                        "tool_name": tool_name,
                        "success": result_success,
                        "message": result_message,
                        "data": result_data,
                    }
                )

            # Build tool results message to send back to LLM
            # This is the key part - feeding results back so LLM can continue
            results_text_parts = []
            for tr in tool_results:
                if tr["success"]:
                    result_str = f"[{tr['tool_name']}] SUCCESS: {tr['message']}"
                    if tr["data"]:
                        result_str += f"\nData: {tr['data']}"
                else:
                    result_str = f"[{tr['tool_name']}] FAILED: {tr['message']}"
                results_text_parts.append(result_str)

            results_message = "\n\n".join(results_text_parts)

            # Add assistant's tool calls and tool results to message history
            # This maintains proper conversation flow
            if content:
                messages.append({"role": "assistant", "content": content})
            else:
                # If LLM only returned tool calls, create a placeholder
                tool_names = [c.get("name", "") for c in tool_calls]
                messages.append(
                    {"role": "assistant", "content": f"[Executing: {', '.join(tool_names)}]"}
                )

            messages.append(
                {
                    "role": "user",
                    "content": f"Tool execution results:\n{results_message}\n\nContinue with the task. If complete, provide a final response to the user.",
                }
            )

            logger.info(
                f"Agentic loop iteration {iteration}: {len(tool_calls)} tools executed, continuing..."
            )

        # Log if we hit the iteration limit
        if iteration >= MAX_TOOL_ITERATIONS:
            logger.warning(f"Agentic loop hit max iterations ({MAX_TOOL_ITERATIONS})")
            final_content = (
                final_content
                or "I've completed several steps but reached my processing limit. Here's what I've done so far."
            )

        # Get final response content
        if not final_content:
            # Look for acknowledge tool message as fallback
            for tool_call in all_tool_calls:
                name = tool_call.get("name", "")
                if name == "acknowledge":
                    args = tool_call.get("args", {})
                    if isinstance(args, str):
                        import json

                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {}
                    ack_message = args.get("message", "")
                    if ack_message:
                        final_content = ack_message
                        break

        self._context.response = final_content
        self._context.tool_calls = all_tool_calls

    # =========================================================================
    # UTILITIES
    # =========================================================================

    def reset(self) -> None:
        """Reset FSM to initial state."""
        self._state = ConciergeState.LISTENING
        self._context = FSMContext()
        self._state_history = [ConciergeState.LISTENING]

    def get_state_history(self) -> List[str]:
        """Get state history as strings."""
        return [s.name for s in self._state_history]
