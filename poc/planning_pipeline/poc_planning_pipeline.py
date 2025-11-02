r"""
PoC 2.4: 4-Stage Planning Pipeline (Sketch → Expand → Validate → Commit)

This PoC implements ADR-0007 in isolation with:
- Stage 1: Sketch (LLM-powered, 150-500ms)
- Stage 2: Expand (deterministic schema filling, <1ms)
- Stage 3: Validate (two-tier: rules <1ms + arbiter 50-100ms)
- Stage 4: Commit (persistence to K0 WAL, <10ms)

Uses shared llm_provider (d:\familyos\poc\llm_provider.py) for LLM calls.

Date: 2025-11-01
Version: 2.0 (FlatBuffers standard + Rich visualization)
"""

import asyncio
import json
import sys
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

sys.path.insert(0, "..")
from llm_provider import get_provider

# ============================================================================
# DATA MODELS (ADR-0011: FlatBuffers structure)
# ============================================================================


class OpType(Enum):
    """Operation type in plan step"""

    TOOL = "Tool"
    MODEL = "Model"
    ASK = "Ask"


class Complexity(Enum):
    """Plan complexity level"""

    SIMPLE = 0
    MEDIUM = 1
    COMPLEX = 2


class Band(Enum):
    """Privacy band level"""

    GREEN = 0
    AMBER = 1
    RED = 2
    BLACK = 3


# Mapping helpers for FlatBuffers serialization
OP_TYPE_TO_INT = {"Tool": 0, "Model": 1, "Ask": 2}
COMPLEXITY_TO_INT = {"simple": 0, "medium": 1, "complex": 2}
BAND_TO_INT = {"GREEN": 0, "AMBER": 1, "RED": 2, "BLACK": 3}


@dataclass
class FlowStep:
    """Single step in execution plan"""

    id: str
    op: OpType
    description: str
    tool: Optional[str] = None
    agent: Optional[str] = None  # Recommended agent for this tool
    schema_in: Optional[Dict] = None
    schema_out: Optional[Dict] = None
    band_required: str = "GREEN"
    caps_required: List[str] = field(default_factory=list)
    est_latency_ms: int = 0
    cost_hint: float = 0.0
    critical: bool = True
    needs: List[str] = field(default_factory=list)  # Dependencies

    def to_dict(self):
        return {
            "id": self.id,
            "op": self.op.value,
            "description": self.description,
            "tool": self.tool,
            "agent": self.agent,
            "band_required": self.band_required,
            "caps_required": self.caps_required,
            "est_latency_ms": self.est_latency_ms,
            "cost_hint": self.cost_hint,
            "needs": self.needs,
        }


@dataclass
class MissingParameterAnalysis:
    """
    Analysis of missing parameters after expansion (M3 Epic 3.1)

    Tracks parameters that are null/empty after expansion,
    indicating the LLM sketch didn't provide complete information.
    """

    has_missing: bool
    missing_params: List[Dict[str, str]] = field(default_factory=list)
    # Each dict: {"step_id": "s1", "param": "time", "tool": "calendar", "description": "..."}


@dataclass
class Sketch:
    """Result of Stage 1: Sketch"""

    intent: str
    steps: List[Dict]
    complexity: str
    raw_output: str
    latency_ms: float
    flatbuffers_buffer: Optional[bytes] = None  # NEW: FlatBuffers binary (from plan_sketch.fbs)


@dataclass
class ExpandedPlan:
    """Result of Stage 2: Expand"""

    intent: str
    steps: List[FlowStep]
    complexity: str
    latency_ms: float
    agents_required: List[str] = field(default_factory=list)  # List of agent IDs needed
    flatbuffers_buffer: Optional[bytes] = None  # NEW: FlatBuffers binary (from plan_node.fbs)


@dataclass
class ValidationResult:
    """Result of Stage 3: Validate"""

    valid: bool
    errors: List[str]
    tier: int  # 1 or 2
    latency_ms: float


@dataclass
class CommitResult:
    """Result of Stage 4: Commit"""

    flow_id: str
    status: str
    latency_ms: float


# ============================================================================
# MOCK REGISTRIES (ADR-0007: Tool + Prompt registries)
# ============================================================================


class ToolRegistry:
    """Mock registry of available tools"""

    TOOLS = {
        "weather": {
            "schema_in": {"location": "str"},
            "schema_out": {"temperature": "int", "condition": "str"},
            "band": "GREEN",
            "caps": [],
            "latency_ms": 200,
            "cost": 0.0,
            "critical": False,
        },
        "calendar": {
            "schema_in": {"action": "str", "date": "str"},
            "schema_out": {"events": "list"},
            "band": "AMBER",
            "caps": ["READ_CALENDAR"],
            "latency_ms": 300,
            "cost": 0.001,
            "critical": True,
        },
        "restaurants": {
            "schema_in": {"location": "str", "cuisine": "str"},
            "schema_out": {"restaurants": "list"},
            "band": "GREEN",
            "caps": [],
            "latency_ms": 250,
            "cost": 0.0,
            "critical": False,
        },
        "reservations": {
            "schema_in": {"restaurant": "str", "time": "str", "party_size": "int"},
            "schema_out": {"confirmation": "str"},
            "band": "AMBER",
            "caps": ["BOOK_RESERVATION"],
            "latency_ms": 500,
            "cost": 0.002,
            "critical": True,
        },
        "messaging": {
            "schema_in": {"recipient": "str", "message": "str"},
            "schema_out": {"sent": "bool"},
            "band": "AMBER",
            "caps": ["SEND_MESSAGE"],
            "latency_ms": 100,
            "cost": 0.0,
            "critical": False,
        },
        "knowledge_graph": {
            "schema_in": {"query": "str"},
            "schema_out": {"results": "list"},
            "band": "AMBER",
            "caps": ["READ_KG"],
            "latency_ms": 150,
            "cost": 0.001,
            "critical": False,
        },
    }

    def get(self, tool_id):
        return self.TOOLS.get(tool_id)


class SessionFixture:
    """Mock user session"""

    def __init__(self, session_id="session_001", band="GREEN", caps=None):
        self.id = session_id
        self.band = band
        self.available_tools = set(ToolRegistry.TOOLS.keys())
        self.capabilities = caps or set()
        self.available_caps = {"READ_CALENDAR", "BOOK_RESERVATION", "SEND_MESSAGE", "READ_KG"}
        self.budget = {
            "latency_ms": 10000,  # 10 second max per turn
            "cost": 1.0,  # $1 max per turn
        }

    def has_capabilities(self, required_caps):
        return all(cap in self.available_caps for cap in required_caps)

    def add_capability(self, cap):
        self.available_caps.add(cap)


# ============================================================================
# AGENT REGISTRY (Parallel to ToolRegistry for multi-agent orchestration)
# ============================================================================


class AgentRegistry:
    """Mock registry of available agents for task delegation"""

    AGENTS = {
        "planner": {
            "description": "Main orchestrator - decides tool/agent routing",
            "capabilities": ["ORCHESTRATE", "PLAN"],
            "max_parallel": 5,
            "band": "GREEN",
        },
        "booking_agent": {
            "description": "Specialized in restaurant/travel reservations",
            "capabilities": ["BOOK_RESERVATION", "READ_CALENDAR"],
            "best_for": ["reservations", "calendar"],
            "band": "AMBER",
        },
        "messenger_agent": {
            "description": "Handles all family communication",
            "capabilities": ["SEND_MESSAGE"],
            "best_for": ["messaging"],
            "band": "AMBER",
        },
        "query_agent": {
            "description": "Handles search and retrieval",
            "capabilities": ["READ_KG"],
            "best_for": ["restaurants", "knowledge_graph", "weather"],
            "band": "GREEN",
        },
    }

    def get(self, agent_id):
        return self.AGENTS.get(agent_id)

    def get_agent_for_tool(self, tool_name):
        """Find best agent for given tool"""
        for agent_id, agent_meta in self.AGENTS.items():
            if "best_for" in agent_meta and tool_name in agent_meta["best_for"]:
                return agent_id
        return None


# ============================================================================
# DYNAMIC PROMPT BUILDER (Generates prompts from registries)
# ============================================================================


class PromptBuilder:
    """Dynamically generates LLM prompts from tool/agent registries"""

    def __init__(self, tool_registry, agent_registry):
        self.tool_registry = tool_registry
        self.agent_registry = agent_registry
        # Cache static prefix (per process)
        self._cached_static_prefix = None
        self._cached_for_tools = None
        self._cached_for_agents = None

    def build_sketch_prompt(self, user_input, session=None):
        """
        Build MINIMAL sketch prompt (ultra-fast, <200 tokens)

        - Tool names only (no descriptions)
        - Agent names only (no descriptions)
        - ONE example only
        - Guardrails + rules-based constraints
        - Cache static prefix, append user input only at runtime

        OPTIMIZED: Reduced from 300 tokens to <200 tokens
        """
        # Get current time for context
        from datetime import datetime

        now = datetime.now()
        day_name = now.strftime("%A")
        date_str = now.strftime("%B %d, %Y")
        time_str = now.strftime("%I:%M %p")
        time_context = f"Current Time: {day_name}, {date_str}, {time_str}"

        # 1. Build tool list (filter if session provided)
        tool_names = list(self.tool_registry.TOOLS.keys())
        if session:
            tool_names = [t for t in tool_names if self._can_access_tool(t, session)]

        # 2. Build agent list
        agent_names = list(self.agent_registry.AGENTS.keys())

        # 3. Check if we can use cached prefix
        if (
            self._cached_static_prefix is not None
            and self._cached_for_tools == tuple(tool_names)
            and self._cached_for_agents == tuple(agent_names)
        ):
            # Use cached prefix, append user input with time context
            return self._cached_static_prefix + f"{time_context}\n\nRequest: {user_input}\nJSON:"

        # 4. Build static prefix (tool list + agent list + one example)
        tool_list = ", ".join(tool_names)
        agent_list = ", ".join(agent_names)

        # OPTIMIZED: Ultra-compact format with uncertainty handling
        static_prefix = f"""Plan with tools. JSON only. ALWAYS include confidence score.
Tools: {tool_list}
Agents: {agent_list}
Format: {{"intent":"<label>","steps":[{{"id":"s1","tool":"<name>","agent":"<agent>","needs":[]}}],"complexity":"simple","confidence":0.XX}}

🚨 CONFIDENCE = "CAN THE PLANNER ACTUALLY EXECUTE THIS?" 🚨
- confidence=0.85+ ONLY if planner has ALL data needed to execute without asking user more questions
- confidence=0.2 if ANYTHING is vague, missing, or requires assumptions
- NEVER assume. NEVER guess. If you'd ask user "which one?", confidence=0.2
- Planner is STRICT world-class planner: it only executes with complete info

WHAT DOES EACH TASK NEED FOR confidence=0.85?
- Book tickets: SPECIFIC city (not "california"), origin, date, time, class (economy/business), passenger count
- Book dinner: SPECIFIC restaurant name, date, time, party size
- Plan trip: SPECIFIC destination city, origin city, dates, budget range, trip duration, number of people
- Remind me: SPECIFIC task, date, time, recurrence (if any)
- Weather: SPECIFIC location
- Search: SPECIFIC query

VAGUE = Low Confidence:
- "california" alone is VAGUE (too many cities). Need San Francisco, LA, San Diego, etc.
- "book tickets" alone is VAGUE. Need: from where? which airport? which date/time?
- "plan a trip" is VAGUE. Need: where from? where to? when? budget?
- "something" or "about something" is ALWAYS vague → confidence=0.2

Examples - FOLLOW EXACTLY:
Input: "book tickets to california"
Output: {{"intent":"needs_clarification","steps":[],"complexity":"simple","confidence":0.2}}
Reason: VAGUE. "California" is not executable - need specific city (SF/LA/SD/etc) + origin + dates + time + class

Input: "book tickets to san francisco from new york economy on 8th november"
Output: {{"intent":"book_tickets","steps":[{{"id":"s1","tool":"travel","agent":"booking_agent","needs":[]}}],"complexity":"simple","confidence":0.85}}
Reason: EXECUTABLE. Has all required data: destination (SF), origin (NY), class (economy), date (8th nov), can infer morning/evening

Input: "book dinner at luigi's tomorrow 7pm"
Output: {{"intent":"book_dinner","steps":[{{"id":"s1","tool":"restaurants","agent":"booking_agent","needs":[]}}],"complexity":"simple","confidence":0.85}}
Reason: EXECUTABLE. Specific restaurant + date + time

Input: "book dinner tomorrow"
Output: {{"intent":"needs_clarification","steps":[],"complexity":"simple","confidence":0.2}}
Reason: VAGUE. Which restaurant? What time? Party size?

Input: "remind me to return parcels tomorrow at 4pm"
Output: {{"intent":"set_reminder","steps":[{{"id":"s1","tool":"calendar","agent":"planner","needs":[]}}],"complexity":"simple","confidence":0.85}}
Reason: EXECUTABLE. Task (return parcels) + time (4pm tomorrow)

Input: "remind me about something tomorrow"
Output: {{"intent":"needs_clarification","steps":[],"complexity":"simple","confidence":0.2}}
Reason: VAGUE. What to remind? What time? "Something" is not executable.

Input: "plan a trip to california"
Output: {{"intent":"needs_clarification","steps":[],"complexity":"simple","confidence":0.2}}
Reason: NOT EXECUTABLE. Missing: specific city, origin, budget, duration, dates, travelers

Input: "plan trip to san francisco from seattle, 3 days, budget 2000, 2 people, nov 8-10"
Output: {{"intent":"plan_trip","steps":[{{"id":"s1","tool":"travel","agent":"planner","needs":[]}}],"complexity":"complex","confidence":0.85}}
Reason: EXECUTABLE. All required info present: destination (SF), origin (Seattle), budget (2000), duration (3 days), travelers (2), dates (Nov 8-10)

Request: """

        # 5. Cache the static prefix
        self._cached_static_prefix = static_prefix
        self._cached_for_tools = tuple(tool_names)
        self._cached_for_agents = tuple(agent_names)

        return static_prefix + f"{time_context}\n\nRequest: {user_input}\nJSON:"

    def _can_access_tool(self, tool_id, session):
        """Check if session can access tool based on band and capabilities"""
        tool = self.tool_registry.get(tool_id)
        if not tool:
            return False

        # Check band restriction
        tool_band = tool.get("band", "GREEN")
        band_order = {"GREEN": 0, "AMBER": 1, "RED": 2, "BLACK": 3}
        if band_order.get(session.band, 0) < band_order.get(tool_band, 0):
            return False

        # Check capability restriction
        required_caps = tool.get("caps", [])
        if required_caps and not session.has_capabilities(required_caps):
            return False

        return True


# ============================================================================
# STAGE 1: SKETCH (LLM-Based High-Level Planning)
# ============================================================================


class SketchStage:
    """Stage 1: Generate high-level plan using LLM (ADR-0007, Stage 1)"""

    def __init__(self, llm_provider, tool_registry=None, agent_registry=None):
        self.llm_provider = llm_provider
        self.tool_registry = tool_registry or ToolRegistry()
        self.agent_registry = agent_registry or AgentRegistry()
        self.prompt_builder = PromptBuilder(self.tool_registry, self.agent_registry)

    async def sketch(self, user_input, session, trace_id="trace_001", tools=None, agents=None):
        """
        Generate sketch plan from user input using dynamic prompt

        Args:
            user_input: User request
            session: User session
            trace_id: Trace ID
            tools: Optional tool registry (uses self.tool_registry if None)
            agents: Optional agent registry (uses self.agent_registry if None)

        Returns: bytes (FlatBuffers serialized Sketch)
        """
        start_time = time.perf_counter()

        # Use provided registries or fallback to instance registries
        tool_reg = tools or self.tool_registry
        agent_reg = agents or self.agent_registry

        # Build dynamic prompt from registries (or create new builder if registries changed)
        if tools or agents:
            prompt_builder = PromptBuilder(tool_reg, agent_reg)
        else:
            prompt_builder = self.prompt_builder

        prompt = prompt_builder.build_sketch_prompt(user_input, session)

        try:
            # Call LLM with strict JSON system message (non-blocking via asyncio.to_thread)
            system_message = "You are a JSON-only assistant. Return ONLY valid JSON without markdown code blocks, explanations, or any other text. Your entire response must be parseable JSON."

            response = await asyncio.to_thread(
                self.llm_provider.call_llm,
                prompt=prompt,
                max_tokens=200,  # OPTIMIZED: Reduced from 256 to 200
                system_message=system_message,
            )

            # Handle empty or invalid response
            sketch_json = None
            if response and response.strip():
                try:
                    # Parse JSON directly (no markdown stripping needed with system message)
                    sketch_json = json.loads(response.strip())
                except json.JSONDecodeError:
                    print("[Sketch] WARNING: Invalid JSON response, using mock plan")
                    print(f"[Sketch] Response was: {response[:200]}")
                    sketch_json = None

            if not sketch_json:
                print("[Sketch] Using mock plan (empty or invalid response)")
                # Return mock plan with ALL FlatBuffers required fields
                sketch_json = {
                    "sketch_id": trace_id,
                    "turn_id": session.id if hasattr(session, "id") else "test_session",
                    "intent": user_input[:50],
                    "steps": [
                        {
                            "id": "step_1",
                            "op": "Tool",
                            "tool": "weather",
                            "description": "Check weather",
                            "needs": [],
                        },
                        {
                            "id": "step_2",
                            "op": "Tool",
                            "tool": "calendar",
                            "description": "Check calendar",
                            "needs": [],
                        },
                    ],
                    "complexity": "simple",
                    "model_id": "mock_model",
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "raw_output": "mock response (LLM failed)",
                }

            # Basic validation
            if "intent" not in sketch_json or "steps" not in sketch_json:
                raise ValueError("Missing intent or steps in sketch")

            latency_ms = (time.perf_counter() - start_time) * 1000

            # M2 Epic 2.1: Extract confidence score (NEW)
            confidence = self._extract_confidence(response, sketch_json)

            print(
                f"[Sketch] Complete: {len(sketch_json['steps'])} steps, "
                f"{latency_ms:.1f}ms, confidence={confidence:.2f}"
            )

            # Convert to FlatBuffers bytes (NEW: ADR-0011)
            try:
                from flatbuffers_serializer import FlatBuffersSerializer

                # Prepare payload with LLM telemetry + FlatBuffers mappings
                sketch_json_with_meta = {
                    **sketch_json,
                    "sketch_id": sketch_json.get("sketch_id", trace_id),
                    "turn_id": sketch_json.get(
                        "turn_id", session.id if hasattr(session, "id") else "turn_unknown"
                    ),
                    "model_id": sketch_json.get("model_id", "groq/llama-3.3-70b-versatile"),
                    "prompt_tokens": sketch_json.get("prompt_tokens", len(prompt.split())),
                    "completion_tokens": sketch_json.get(
                        "completion_tokens", len(response.split()) if response else 0
                    ),
                    "llm_latency_ms": int(latency_ms),
                    "raw_output": sketch_json.get("raw_output", response if response else ""),
                    "complexity_int": COMPLEXITY_TO_INT.get(
                        sketch_json.get("complexity", "medium"), 1
                    ),
                    "confidence": confidence,  # M2: Store confidence for pipeline use
                }

                # Map string op types to integers for FlatBuffers
                for step in sketch_json_with_meta.get("steps", []):
                    if "op" in step and isinstance(step["op"], str):
                        step["op"] = OP_TYPE_TO_INT.get(step["op"], 0)

                # Serialize to FlatBuffers bytes
                flatbuffers_bytes = FlatBuffersSerializer.serialize_sketch(
                    sketch_json_with_meta, model_id="sketch_stage", latency_ms=latency_ms
                )
                print(f"[Sketch] Serialized to FB: {len(flatbuffers_bytes)} bytes")

                # Return FlatBuffers bytes (not Sketch object)
                return flatbuffers_bytes

            except ImportError:
                print("[Sketch] WARNING: flatbuffers_serializer not available")
                raise
            except Exception as e:
                print(f"[Sketch] WARNING: FlatBuffers serialization failed: {e}")
                raise

        except Exception as e:
            print(f"[Sketch] ERROR: {e}")
            raise

    def _extract_confidence(self, llm_response: str, parsed_json: Optional[dict]) -> float:
        """
        Extract or estimate confidence score from LLM response

        M2 Epic 2.1: Confidence extraction heuristics

        Heuristics:
        - JSON parse failed → 0.3 (low confidence)
        - JSON valid but missing required fields → 0.5 (medium)
        - JSON valid, has steps but incomplete → 0.65 (medium-high)
        - JSON valid with all fields → 0.85 (high)

        Args:
            llm_response: Raw LLM response string
            parsed_json: Parsed JSON dict (or None if parse failed)

        Returns:
            Confidence score 0.0-1.0
        """
        # Parse failed or no response
        if parsed_json is None or not llm_response:
            return 0.3

        # Check for required fields
        required_fields = ["intent", "steps"]
        missing_fields = [f for f in required_fields if f not in parsed_json]

        if missing_fields:
            return 0.5  # Missing required fields

        # Check if steps are valid
        steps = parsed_json.get("steps", [])
        if not steps or not isinstance(steps, list):
            return 0.6  # Empty or invalid steps list

        # Check if all steps have required fields
        step_completeness_score = 0
        for step in steps:
            # Essential fields for a step
            required_step_fields = ["id", "tool", "needs"]
            has_all_fields = all(k in step for k in required_step_fields)

            if has_all_fields:
                step_completeness_score += 1

        if len(steps) > 0:
            completeness_ratio = step_completeness_score / len(steps)

            # Map completeness to confidence
            if completeness_ratio == 1.0:
                return 0.85  # All steps complete
            elif completeness_ratio >= 0.8:
                return 0.75  # Most steps complete
            elif completeness_ratio >= 0.5:
                return 0.65  # Half complete
            else:
                return 0.55  # Less than half complete

        # Fallback: JSON valid with required fields
        return 0.7


# ============================================================================
# STAGE 2: EXPAND (Deterministic Schema Filling)
# ============================================================================


class ExpandStage:
    """Stage 2: Fill tool schemas from registry (ADR-0007, Stage 2)"""

    def __init__(self, tool_registry, agent_registry=None):
        self.tool_registry = tool_registry
        self.agent_registry = agent_registry or AgentRegistry()

        # Lazy cache: built on first use
        self._tool_to_agent_cache = None

    def _get_tool_to_agent_map(self, agent_reg):
        """Build and cache tool→agent mapping on first use"""
        if self._tool_to_agent_cache is None:
            self._tool_to_agent_cache = {}
            for agent_id, agent_meta in agent_reg.AGENTS.items():
                if "best_for" in agent_meta:
                    for tool in agent_meta["best_for"]:
                        self._tool_to_agent_cache[tool] = agent_id
        return self._tool_to_agent_cache

    def expand(self, sketch_bytes, session, trace_id="trace_001", tools=None, agents=None):
        """
        Fill in tool schemas from registry and add agent recommendations

        Args:
            sketch_bytes: FlatBuffers bytes from stage 1 (NOT Sketch object)
            session: User session
            trace_id: Trace ID
            tools: Optional tool registry (uses self.tool_registry if None)
            agents: Optional agent registry (uses self.agent_registry if None)

        Returns: bytes (FlatBuffers serialized ExpandedPlan)
        """
        start_time = time.perf_counter()

        # Use provided registries or fallback to instance registries
        tool_reg = tools or self.tool_registry
        agent_reg = agents or self.agent_registry

        # Parse FlatBuffers bytes to dict
        from flatbuffers_serializer import FlatBuffersSerializer, flatbuffers_to_dict

        sketch_dict = flatbuffers_to_dict(sketch_bytes)
        steps_to_process = sketch_dict.get("steps", [])

        expanded_steps = []
        errors = []
        agents_used = set()

        for step_dict in steps_to_process:
            # Parse step if it's a dict
            if isinstance(step_dict, dict):
                step_op = step_dict.get("op", "Tool")
                step_id = step_dict.get("id", f"step_{len(expanded_steps)}")
                step_description = step_dict.get("description", "")
                step_tool = step_dict.get("tool")
                step_agent = step_dict.get("agent")  # Agent from LLM (if provided)
                step_needs = step_dict.get("needs", [])
            else:
                step_op = step_dict.op
                step_id = step_dict.id
                step_description = step_dict.description
                step_tool = step_dict.tool
                step_agent = step_dict.agent if hasattr(step_dict, "agent") else None
                step_needs = step_dict.needs

            if step_op != "Tool":
                # Non-tool steps don't need expansion
                expanded_steps.append(step_dict)
                continue

            if not step_tool:
                errors.append(f"Step {step_id} missing tool name")
                continue

            # Lookup tool in registry
            tool_spec = tool_reg.get(step_tool)
            if not tool_spec:
                errors.append(f"Unknown tool: {step_tool}")
                continue

            # If LLM didn't provide agent, look it up using cache
            if not step_agent:
                tool_to_agent_map = self._get_tool_to_agent_map(agent_reg)
                step_agent = tool_to_agent_map.get(step_tool)

            if step_agent:
                agents_used.add(step_agent)

            # Create expanded step
            expanded_step = FlowStep(
                id=step_id,
                op=OpType.TOOL,
                description=step_description,
                tool=step_tool,
                agent=step_agent,  # Include agent recommendation
                schema_in=tool_spec["schema_in"],
                schema_out=tool_spec["schema_out"],
                band_required=tool_spec["band"],
                caps_required=tool_spec["caps"],
                est_latency_ms=tool_spec["latency_ms"],
                cost_hint=tool_spec["cost"],
                critical=tool_spec["critical"],
                needs=step_needs,
            )

            expanded_steps.append(expanded_step)

        latency_ms = (time.perf_counter() - start_time) * 1000

        print(f"[Expand] Complete: {len(expanded_steps)} steps, {latency_ms:.2f}ms")

        if errors:
            print(f"[Expand] Warnings: {errors}")

        # Serialize expanded plan to FlatBuffers bytes (NEW: ADR-0011)
        expanded_dict = {
            "intent": sketch_dict.get("intent", ""),
            "steps": [s.to_dict() if hasattr(s, "to_dict") else s for s in expanded_steps],
            "complexity": sketch_dict.get("complexity", "medium"),
            "agents_required": sorted(list(agents_used)),
        }

        flatbuffers_bytes = FlatBuffersSerializer.serialize_expanded_plan(
            expanded_dict, model_id="expand_stage", latency_ms=latency_ms
        )
        print(f"[Expand] Serialized to FB: {len(flatbuffers_bytes)} bytes")

        # Return FlatBuffers bytes (not ExpandedPlan object)
        return flatbuffers_bytes


# ============================================================================
# M3 EPIC 3.1: MISSING PARAMETER DETECTION
# ============================================================================


def detect_missing_parameters(expanded_plan_dict: dict) -> MissingParameterAnalysis:
    """
    Detect missing required parameters after expansion (M3 Epic 3.1)

    Checks each step for null/empty parameter values in schema_in,
    indicating incomplete information from the LLM sketch.

    Args:
        expanded_plan_dict: Expanded plan as dict (from flatbuffers_to_dict)

    Returns:
        MissingParameterAnalysis with has_missing flag and list of missing params
    """
    missing = []

    for step in expanded_plan_dict.get("steps", []):
        step_id = step.get("id", "unknown")
        step_tool = step.get("tool", "unknown")
        step_description = step.get("description", "")

        # Check schema_in for null/empty values
        schema_in = step.get("schema_in", {})

        if isinstance(schema_in, dict):
            for param_name, param_value in schema_in.items():
                # Check if parameter is missing (null, None, empty string)
                if param_value is None or param_value == "" or param_value == "null":
                    missing.append(
                        {
                            "step_id": step_id,
                            "param": param_name,
                            "tool": step_tool,
                            "step_description": step_description,
                        }
                    )

    return MissingParameterAnalysis(has_missing=len(missing) > 0, missing_params=missing)


# ============================================================================
# STAGE 3: VALIDATE (Two-Tier)
# ============================================================================


class ValidateTier1:
    """Stage 3 Tier 1: Rule-based validation (ADR-0007, Stage 3 Tier 1)"""

    def __init__(self):
        pass

    def validate(self, plan_bytes, session, trace_id="trace_001"):
        """
        Rule-based validation on FlatBuffers data

        Args:
            plan_bytes: FlatBuffers bytes from stage 2 (NOT ExpandedPlan object)
            session: User session
            trace_id: Trace ID

        Returns: ValidationResult
        """
        start_time = time.perf_counter()

        # Parse FlatBuffers bytes to dict
        from flatbuffers_serializer import flatbuffers_to_dict

        plan_dict = flatbuffers_to_dict(plan_bytes)
        steps = plan_dict.get("steps", [])

        # Numeric band map (replaces string comparisons)
        BAND_MAP = {"GREEN": 0, "AMBER": 1, "RED": 2, "BLACK": 3}

        errors = []

        # 1. Structure checks (short-circuit on first fatal error)
        if not steps:
            errors.append("Plan has no steps")
            return ValidationResult(
                valid=False, errors=errors, tier=1, latency_ms=time.perf_counter() - start_time
            )

        if len(steps) > 12:
            errors.append("Plan too complex (max 12 steps)")
            return ValidationResult(
                valid=False, errors=errors, tier=1, latency_ms=time.perf_counter() - start_time
            )

        # 2. DAG validation (cycle detection)
        if self._has_cycle(steps):
            errors.append("Plan has circular dependencies")
            return ValidationResult(
                valid=False, errors=errors, tier=1, latency_ms=time.perf_counter() - start_time
            )

        # 3. Capability validation
        for step in steps:
            step_op = step.get("op", "Tool")
            if step_op == "Tool":
                step_tool = step.get("tool")
                step_caps = step.get("caps_required", [])
                step_band = step.get("band_required", "GREEN")

                # Check tool available
                if step_tool and step_tool not in session.available_tools:
                    errors.append(f"Tool '{step_tool}' not available in session")
                    return ValidationResult(
                        valid=False,
                        errors=errors,
                        tier=1,
                        latency_ms=time.perf_counter() - start_time,
                    )

                # Check capabilities
                if step_caps and not session.has_capabilities(step_caps):
                    errors.append(f"Missing capabilities for {step_tool}: {step_caps}")
                    return ValidationResult(
                        valid=False,
                        errors=errors,
                        tier=1,
                        latency_ms=time.perf_counter() - start_time,
                    )

                # Check band (numeric comparison)
                session_band_num = BAND_MAP.get(session.band, 0)
                step_band_num = BAND_MAP.get(step_band, 0)
                if session_band_num < step_band_num:
                    errors.append(
                        f"Band {session.band} cannot access {step_band} tool '{step_tool}'"
                    )
                    return ValidationResult(
                        valid=False,
                        errors=errors,
                        tier=1,
                        latency_ms=time.perf_counter() - start_time,
                    )

        # 4. Budget validation
        total_latency = sum(s.get("est_latency_ms", 0) for s in steps)
        if total_latency > session.budget["latency_ms"]:
            errors.append(
                f"Plan exceeds latency budget: {total_latency}ms > {session.budget['latency_ms']}ms"
            )
            return ValidationResult(
                valid=False, errors=errors, tier=1, latency_ms=time.perf_counter() - start_time
            )

        total_cost = sum(s.get("cost_hint", 0) for s in steps)
        if total_cost > session.budget["cost"]:
            errors.append(
                f"Plan exceeds cost budget: ${total_cost:.3f} > ${session.budget['cost']:.3f}"
            )
            return ValidationResult(
                valid=False, errors=errors, tier=1, latency_ms=time.perf_counter() - start_time
            )

        latency_ms = (time.perf_counter() - start_time) * 1000

        status = "PASS" if not errors else "FAIL"
        print(f"[Validate Tier1] {status}: {len(errors)} errors, {latency_ms:.2f}ms")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            tier=1,
            latency_ms=latency_ms,
        )

    def _has_cycle(self, steps):
        """Detect circular dependencies using DFS (on dict objects)"""
        # Build adjacency list
        graph = defaultdict(list)
        for step in steps:
            # Handle dict objects (from FlatBuffers)
            step_id = step.get("id", "")
            step_needs = step.get("needs", [])

            for dep in step_needs:
                graph[dep].append(step_id)

        # DFS cycle detection
        visited = set()
        rec_stack = set()

        def dfs(node):
            if node in rec_stack:
                return True
            if node in visited:
                return False

            visited.add(node)
            rec_stack.add(node)

            for neighbor in graph.get(node, []):
                if dfs(neighbor):
                    return True

            rec_stack.remove(node)
            return False

        # Check all nodes
        for step in steps:
            step_id = step.get("id", "")
            if dfs(step_id):
                return True

        return False


class ValidateTier2:
    """Stage 3 Tier 2: LLM-based safety check (ADR-0007, Stage 3 Tier 2)"""

    def __init__(self, llm_provider):
        self.llm_provider = llm_provider

    async def check_safety(self, plan_bytes, session, trace_id="trace_001"):
        """
        LLM-based safety check on FlatBuffers data (only for risky plans)

        Args:
            plan_bytes: FlatBuffers bytes from stage 2
            session: User session
            trace_id: Trace ID

        Returns: ValidationResult
        """
        # Parse FlatBuffers bytes to dict
        from flatbuffers_serializer import flatbuffers_to_dict

        plan_dict = flatbuffers_to_dict(plan_bytes)
        steps = plan_dict.get("steps", [])

        # Decide: Should we invoke arbiter?
        if not self._should_invoke(steps, session, plan_dict.get("complexity", "medium")):
            return ValidationResult(
                valid=True,
                errors=[],
                tier=2,
                latency_ms=0,
            )

        start_time = time.perf_counter()

        # Build minimal safety prompt (only essential fields)
        step_summaries = []
        for step in steps:
            step_summaries.append(
                {
                    "id": step.get("id"),
                    "tool": step.get("tool"),
                    "band": step.get("band_required", "GREEN"),
                    "needs": step.get("needs", []),
                }
            )

        prompt = f"""Safety check: can this plan run?
Intent: {plan_dict.get('intent', '')}
Steps: {json.dumps(step_summaries, indent=2)}
User band: {session.band}

Answer: {{"safe": true/false, "reason": "brief"}}
JSON only:"""

        try:
            # Call arbiter LLM (non-blocking)
            response = await asyncio.to_thread(
                self.llm_provider.call_llm,
                prompt=prompt,
                max_tokens=100,
            )

            result = json.loads(response)

            latency_ms = (time.perf_counter() - start_time) * 1000

            safe = result.get("safe", True)
            errors = [] if safe else [f"Arbiter: {result.get('reason', 'Unsafe plan')}"]

            status = "SAFE" if safe else "UNSAFE"
            print(f"[Validate Tier2] {status}: {result.get('reason', '')}, {latency_ms:.1f}ms")

            return ValidationResult(
                valid=safe,
                errors=errors,
                tier=2,
                latency_ms=latency_ms,
            )

        except Exception as e:
            print(f"[Validate Tier2] ERROR: {e}")
            # Default to unsafe (fail-closed)
            return ValidationResult(
                valid=False,
                errors=[f"Arbiter error: {e}"],
                tier=2,
                latency_ms=time.perf_counter() - start_time,
            )

    def _should_invoke(self, steps, session, complexity):
        """
        Decide if arbiter needed (AGGRESSIVE SKIPPING for speed)

        Skip arbiter for:
        - Simple plans (1-2 steps) with low complexity
        - GREEN band sessions (lowest risk classification)
        - Plans with only GREEN-band tools (no sensitive operations)
        - All GREEN steps

        Args:
            steps: List of step dicts from FlatBuffers
            session: User session
            complexity: Complexity string from plan
        """
        # Numeric band map
        BAND_MAP = {"GREEN": 0, "AMBER": 1, "RED": 2, "BLACK": 3}

        # Quick Win 1: Skip arbiter for simple, low-risk plans
        if len(steps) <= 2 and complexity == "simple":
            print("[Validate Tier2] Skipping arbiter (simple plan, ≤2 steps)")
            return False

        # Quick Win 2: Skip for GREEN band users (lowest risk)
        if session.band == "GREEN":
            print("[Validate Tier2] Skipping arbiter (GREEN band user)")
            return False

        # Quick Win 3: Skip if all tools are GREEN band (no sensitive data access)
        step_bands = [step.get("band_required", "GREEN") for step in steps]
        all_green = all(band == "GREEN" for band in step_bands)
        if all_green:
            print("[Validate Tier2] Skipping arbiter (all steps GREEN band)")
            return False

        # Only invoke for AMBER+ band or complex plans
        max_step_band_num = max((BAND_MAP.get(band, 0) for band in step_bands), default=0)

        # Only invoke for AMBER+ if 3+ steps (multi-tool complexity)
        if max_step_band_num >= BAND_MAP.get("AMBER", 1) and len(steps) >= 3:
            print(f"[Validate Tier2] Invoking arbiter (AMBER+ band, {len(steps)} steps)")
            return True

        return False


# ============================================================================
# STAGE 4: COMMIT (Persistence)
# ============================================================================


class CommitStage:
    """Stage 4: Persist plan to K0 WAL (ADR-0007, Stage 4)"""

    def __init__(self, use_flatbuffers=False):
        self.committed_plans = {}  # Simulate K0 WAL
        self.use_flatbuffers = use_flatbuffers

        # Import FlatBuffers serializer if requested
        if use_flatbuffers:
            try:
                from flatbuffers_serializer import FlatBuffersSerializer

                self.fb_serializer = FlatBuffersSerializer()
            except ImportError:
                print("[Commit] WARNING: FlatBuffers not available, using JSON")
                self.use_flatbuffers = False

    async def commit(self, plan_bytes, session, trace_id="trace_001", pipeline_latency_ms=0.0):
        """
        Commit plan to durable storage (FlatBuffers-only path)

        Args:
            plan_bytes: FlatBuffers bytes from stage 3 (ExpandedPlan)
            session: User session
            trace_id: Trace ID
            pipeline_latency_ms: Total E2E pipeline latency

        Returns: CommitResult
        """
        start_time = time.perf_counter()

        # Parse FlatBuffers bytes to extract metadata
        from flatbuffers_serializer import FlatBuffersSerializer, flatbuffers_to_dict

        plan_dict = flatbuffers_to_dict(plan_bytes)

        # Create FlowDef as FlatBuffers bytes (NO JSON fallback)
        flow_id = str(uuid.uuid4())

        # Serialize to FlatBuffers (pure binary, no JSON)
        flow_def_bytes = FlatBuffersSerializer.serialize_flow_def(
            flow_id=flow_id,
            expanded={
                "intent": plan_dict.get("intent", ""),
                "complexity": plan_dict.get("complexity", 1),
                "agents_required": plan_dict.get("agents_required", []),
                "steps": plan_dict.get("steps", []),
            },
            session=session,
            trace_id=trace_id,
            pipeline_latency_ms=pipeline_latency_ms,
        )

        # Write to K0 WAL (simulated as in-memory storage in PoC)
        # Store only bytes (no JSON)
        self.committed_plans[flow_id] = {
            "data": flow_def_bytes,
            "format": "FlatBuffers",
            "timestamp": datetime.now().isoformat(),
        }

        latency_ms = (time.perf_counter() - start_time) * 1000

        print(f"[Commit] Complete: {flow_id}, {latency_ms:.2f}ms (FB bytes only)")

        return CommitResult(
            flow_id=flow_id,
            status="COMMITTED",
            latency_ms=latency_ms,
        )


# ============================================================================
# PLANNING PIPELINE ORCHESTRATOR
# ============================================================================


class PlanningPipeline:
    """Full 4-stage planning pipeline (ADR-0007) with dynamic injection"""

    def __init__(
        self,
        llm_provider,
        tool_registry=None,
        agent_registry=None,
        use_flatbuffers=False,
        enable_clarifications=False,
    ):
        self.llm_provider = llm_provider

        # Pipeline-level registries (can be injected at init time)
        self.tool_registry = tool_registry or ToolRegistry()
        self.agent_registry = agent_registry or AgentRegistry()
        self.use_flatbuffers = use_flatbuffers

        # Stages (use pipeline-level registries)
        self.sketch_stage = SketchStage(llm_provider, self.tool_registry, self.agent_registry)
        self.expand_stage = ExpandStage(self.tool_registry, self.agent_registry)
        self.validate_tier1 = ValidateTier1()
        self.validate_tier2 = ValidateTier2(llm_provider)
        self.commit_stage = CommitStage(use_flatbuffers=use_flatbuffers)

        # HITL Clarification System (M1: Epic 1.3)
        self.enable_clarifications = enable_clarifications
        self.clarification_manager = None
        self.input_handler = None
        self.return_clarifications = False  # NEW: For Concierge integration

        if enable_clarifications:
            try:
                from clarification_manager import ClarificationManager
                from interactive_input import InteractiveInputHandler

                self.clarification_manager = ClarificationManager(
                    llm_provider=llm_provider,
                    config={
                        "max_clarifications": 2,
                        "execute_threshold": 0.6,
                        "clarify_threshold": 0.4,
                        "reject_threshold": 0.0,
                    },
                )
                self.input_handler = InteractiveInputHandler()
                print("[Pipeline] ✅ HITL clarification system enabled")
            except ImportError as e:
                print(f"[Pipeline] ⚠️  Could not enable clarifications: {e}")
                self.enable_clarifications = False

        # Metrics
        self.metrics = {
            "total_plans": 0,
            "successful_plans": 0,
            "failed_validations": 0,
            "arbiter_invocations": 0,
        }

    def inject_tools(self, new_tools_dict):
        """Inject/update tools at pipeline level"""
        if isinstance(new_tools_dict, dict):
            self.tool_registry.TOOLS.update(new_tools_dict)
        else:
            # If it's a new registry, replace it
            self.tool_registry = new_tools_dict

        # Invalidate expand stage cache
        self.expand_stage._tool_to_agent_cache = None
        print(f"[Pipeline] Injected {len(new_tools_dict)} tools")

    def inject_agents(self, new_agents_dict):
        """Inject/update agents at pipeline level"""
        if isinstance(new_agents_dict, dict):
            self.agent_registry.AGENTS.update(new_agents_dict)
        else:
            # If it's a new registry, replace it
            self.agent_registry = new_agents_dict

        # Invalidate expand stage cache
        self.expand_stage._tool_to_agent_cache = None
        print(f"[Pipeline] Injected {len(new_agents_dict)} agents")

    async def plan(
        self, user_input, session, trace_id="trace_001", request_tools=None, request_agents=None
    ):
        """
        Full planning pipeline with optional request-level tool/agent injection

        Args:
            user_input: User request
            session: User session with capabilities/band
            trace_id: Trace ID for logging
            request_tools: Optional dict of tools specific to this request
            request_agents: Optional dict of agents specific to this request

        Returns: dict with flow_id, status, latencies, and visualization data
        """
        viz = VisualizationHelper()

        viz.print_header(f"PLANNING: {user_input}")

        total_start = time.perf_counter()

        # REQUEST-LEVEL INJECTION: Create temporary registries if provided
        if request_tools or request_agents:
            # Use request-level tools/agents (merged with pipeline-level)
            effective_tools = ToolRegistry()
            effective_tools.TOOLS = {**self.tool_registry.TOOLS}  # Copy pipeline tools
            if request_tools:
                effective_tools.TOOLS.update(request_tools)  # Add/override with request tools

            effective_agents = AgentRegistry()
            effective_agents.AGENTS = {**self.agent_registry.AGENTS}  # Copy pipeline agents
            if request_agents:
                effective_agents.AGENTS.update(request_agents)  # Add/override with request agents

            print(
                f"\n📦 Using {len(effective_tools.TOOLS)} tools, {len(effective_agents.AGENTS)} agents"
            )
        else:
            # Use pipeline-level registries
            effective_tools = self.tool_registry
            effective_agents = self.agent_registry

        try:
            # STAGE 1: SKETCH (with effective registries, returns FB bytes)
            viz.print_stage_header(1, "SKETCH (LLM)")
            sketch_start = time.perf_counter()
            sketch_bytes = await self.sketch_stage.sketch(
                user_input, session, trace_id, tools=effective_tools, agents=effective_agents
            )
            sketch_latency_ms = (time.perf_counter() - sketch_start) * 1000

            # Parse for visualization
            from flatbuffers_serializer import flatbuffers_to_dict

            sketch_dict = flatbuffers_to_dict(sketch_bytes)
            viz.print_query_analysis(user_input, sketch_dict.get("raw_output", ""), sketch_dict)
            print(f"\n⏱️  Latency: {sketch_latency_ms:.1f}ms")

            # M2 EPIC 2.2: CLARIFICATION HOOK AFTER SKETCH (NEW)
            if self.enable_clarifications and self.clarification_manager:
                confidence = sketch_dict.get("confidence", 0.7)  # Default to 0.7 if not set
                intent = sketch_dict.get("intent", "unknown")

                # CONFIDENCE GATING: Planner is strict - only proceeds with high confidence
                # If confidence is too low, hand off to Concierge for more context
                CONFIDENCE_THRESHOLD = 0.6  # Minimum confidence to proceed

                # Check for BOTH explicit needs_clarification AND low confidence
                needs_clarification = (
                    intent == "needs_clarification" or confidence < CONFIDENCE_THRESHOLD
                )

                if needs_clarification:
                    print(
                        f"[Pipeline] Confidence gate triggered (confidence={confidence:.2f}, threshold={CONFIDENCE_THRESHOLD})"
                    )
                    if intent == "needs_clarification":
                        print("[Pipeline] LLM explicitly signaled needs_clarification")
                    else:
                        print(
                            f"[Pipeline] Confidence too low ({confidence:.2f} < {CONFIDENCE_THRESHOLD})"
                        )
                    print("[Pipeline] Handing off to Concierge for clarification...")

                    # Build conversation history for context
                    # Get time context for better temporal understanding
                    from datetime import datetime

                    now = datetime.now()
                    day_name = now.strftime("%A")
                    date_str = now.strftime("%B %d, %Y")
                    time_str = now.strftime("%I:%M %p")
                    time_context = f"Current Time: {day_name}, {date_str}, {time_str}"

                    conversation_context = ""
                    if self.clarification_manager.state.responses:
                        conversation_context = "\n\nPrevious conversation:\n"
                        for i, resp in enumerate(self.clarification_manager.state.responses, 1):
                            conversation_context += f"  Round {i}: {resp}\n"

                    # Generate empathetic, personalized clarification using LLM
                    empathy_prompt = f"""You are a caring, empathetic AI assistant. The user said: "{user_input}"{conversation_context}

{time_context}

You need to ask for clarification, but do it in a warm, understanding way. Consider the user's emotional state if apparent.

Guidelines:
- Be warm and supportive
- Acknowledge any emotions expressed (if any)
- Build on what the user already told you - don't repeat questions
- Gently ask what SPECIFIC ACTION they want to take
- Keep it brief and natural (1-2 sentences max)
- End with an open, actionable question
- Use current time context for temporal questions (e.g., "what time today?" vs "what time tomorrow?")

Generate a single, caring clarification question:"""

                    try:
                        # Call LLM for empathetic clarification
                        empathetic_response = await asyncio.to_thread(
                            self.llm_provider.call_llm,
                            prompt=empathy_prompt,
                            max_tokens=100,
                            system_message="You are a compassionate assistant. Respond with only the clarification question, no explanations.",
                        )

                        clarification_q = (
                            empathetic_response.strip()
                            if empathetic_response
                            else ("I understand. What would you like me to help you with?")
                        )
                    except Exception as e:
                        # Fallback to friendly default
                        print(f"[Pipeline] Could not generate empathetic response: {e}")
                        clarification_q = (
                            "I hear you. What would you like me to help you with right now?"
                        )

                    # NEW: If return_clarifications mode, return instead of prompting
                    if self.return_clarifications:
                        return {
                            "status": "NEEDS_CLARIFICATION",
                            "question": clarification_q,
                            "context": {
                                "user_input": user_input,
                                "conversation_history": self.clarification_manager.state.responses,
                                "intent": intent,
                                "confidence": confidence,
                            },
                            "total_latency_ms": sketch_latency_ms,
                        }

                    # LEGACY: Direct prompting mode (for backward compatibility)
                    if self.input_handler:
                        user_response = self.input_handler.prompt_user(clarification_q)

                        if user_response:
                            # Retry with clarified input
                            self.clarification_manager.add_user_response(user_response)
                            self.input_handler.show_info("Got it! Let me help you with that...")

                            return await self.plan(
                                f"{user_input}. {user_response}",
                                session,
                                trace_id,
                                request_tools,
                                request_agents,
                            )
                        else:
                            self.input_handler.show_warning("No problem, I'm here if you need me.")
                            return {
                                "status": "REJECTED",
                                "reason": "User chose not to proceed",
                                "total_latency_ms": sketch_latency_ms,
                            }  # Create IntentAnalysis for clarification decision
                from clarification_manager import IntentAnalysis

                analysis = IntentAnalysis(
                    intent=intent,
                    confidence=confidence,
                    missing_entities=[],  # Will be detected in Expand stage
                    original_query=user_input,
                )

                decision = self.clarification_manager.should_clarify(analysis)

                if decision == "CLARIFY":
                    # Determine strategy based on confidence level
                    if confidence < 0.6:
                        strategy = "simplify"  # Medium confidence
                    else:
                        strategy = "missing_entity"  # High confidence but needs more

                    # Generate clarification question
                    clarification_q = await self.clarification_manager.generate_clarification(
                        analysis, strategy=strategy
                    )

                    # Prompt user for clarification
                    user_response = self.input_handler.prompt_user(clarification_q)

                    if user_response:
                        # User provided clarification, retry with clarified input
                        clarified_query = f"{user_input}. {user_response}"
                        self.clarification_manager.add_user_response(user_response)

                        self.input_handler.show_info(
                            f"Retrying with clarified input: {clarified_query[:80]}..."
                        )

                        # RECURSIVE RETRY with clarified input
                        return await self.plan(
                            clarified_query, session, trace_id, request_tools, request_agents
                        )
                    else:
                        # User cancelled, proceed with best effort
                        self.input_handler.show_warning(
                            "Clarification cancelled, proceeding with best effort..."
                        )

                elif decision == "REJECT":
                    # Confidence too low, ask to rephrase entirely
                    rephrase_q = await self.clarification_manager.generate_clarification(
                        analysis, strategy="rephrase"
                    )

                    user_response = self.input_handler.prompt_user(rephrase_q)

                    if user_response:
                        # User rephrased, retry with new query
                        self.clarification_manager.add_user_response(user_response)
                        self.input_handler.show_info("Retrying with rephrased query...")

                        # RETRY with completely new query
                        return await self.plan(
                            user_response, session, trace_id, request_tools, request_agents
                        )
                    else:
                        # User cancelled, cannot proceed
                        self.input_handler.show_error(
                            "Confidence too low to proceed, clarification cancelled"
                        )
                        return {
                            "status": "REJECTED",
                            "error": "Confidence too low, user cancelled clarification",
                            "confidence": confidence,
                            "total_latency_ms": (time.perf_counter() - total_start) * 1000,
                        }

                # If EXECUTE, proceed to next stage (no action needed)

            # STAGE 2: EXPAND (input: FB bytes, output: FB bytes)
            viz.print_stage_header(2, "EXPAND (Schema Lookup)")
            expand_start = time.perf_counter()
            expanded_bytes = self.expand_stage.expand(
                sketch_bytes, session, trace_id, tools=effective_tools, agents=effective_agents
            )
            expand_latency_ms = (time.perf_counter() - expand_start) * 1000

            expanded_dict = flatbuffers_to_dict(expanded_bytes)
            viz.print_plan_steps(expanded_dict.get("steps", []), show_details=True)
            print(f"\n⏱️  Latency: {expand_latency_ms:.2f}ms")

            # M3 EPIC 3.2: MISSING PARAMETER CLARIFICATION HOOK (NEW)
            if self.enable_clarifications and self.clarification_manager:
                # Detect missing parameters after expansion
                missing_analysis = detect_missing_parameters(expanded_dict)

                if missing_analysis.has_missing:
                    # Build human-readable list of missing params
                    missing_params_list = []
                    for m in missing_analysis.missing_params:
                        param_desc = f"{m['param']} for {m['tool']}"
                        if m["step_description"]:
                            param_desc += f" ({m['step_description']})"
                        missing_params_list.append(param_desc)

                    missing_params_str = ", ".join(
                        missing_params_list[:3]
                    )  # Limit to 3 for readability
                    if len(missing_params_list) > 3:
                        missing_params_str += f" and {len(missing_params_list) - 3} more"

                    # Create IntentAnalysis for clarification
                    from clarification_manager import IntentAnalysis

                    analysis = IntentAnalysis(
                        intent=expanded_dict.get("intent", "unknown"),
                        confidence=0.8,  # High confidence in intent, just missing data
                        missing_entities=[m["param"] for m in missing_analysis.missing_params],
                        original_query=user_input,
                    )

                    # Generate clarification question using "missing_entity" strategy
                    clarification_q = await self.clarification_manager.generate_clarification(
                        analysis, strategy="missing_entity"
                    )

                    # Show which parameters are missing
                    self.input_handler.show_warning(
                        f"Missing required information: {missing_params_str}"
                    )

                    # Prompt user for missing parameters
                    user_response = self.input_handler.prompt_user(clarification_q)

                    if user_response:
                        # User provided missing info, retry sketch with additional data
                        clarified_query = f"{user_input}. {user_response}"
                        self.clarification_manager.add_user_response(user_response)

                        self.input_handler.show_info("Retrying with additional information...")

                        # RECURSIVE RETRY with clarified input (re-run from sketch)
                        return await self.plan(
                            clarified_query, session, trace_id, request_tools, request_agents
                        )
                    else:
                        # User cancelled, proceed with best effort (missing params)
                        self.input_handler.show_warning(
                            "Proceeding with incomplete information (some parameters missing)..."
                        )

            # STAGE 3A: VALIDATE TIER 1 (input: FB bytes)
            viz.print_stage_header(3, "VALIDATE (Tier 1 - Rules)")
            validation_t1 = self.validate_tier1.validate(expanded_bytes, session, trace_id)

            if not validation_t1.valid:
                self.metrics["failed_validations"] += 1
                viz.print_validation_result(
                    {
                        "valid": False,
                        "errors": validation_t1.errors,
                        "latency_ms": validation_t1.latency_ms,
                    }
                )

                # M4 Epic 4.2: Clarification hook after Tier 1 validation failure
                if self.enable_clarifications and self.clarification_manager:
                    from clarification_manager import ClarificationDecision

                    self._logger.warning(
                        f"Tier 1 validation failed with {len(validation_t1.errors)} error(s). "
                        "Asking user for clarification..."
                    )

                    # Create analysis with validation failure (medium confidence - plan created but invalid)
                    analysis = IntentAnalysis(
                        intent=expanded_dict.get("intent", "unknown"),
                        confidence=0.5,  # Medium confidence (plan was created but invalid)
                        missing_entities=[],
                        original_query=user_input,
                    )

                    decision = self.clarification_manager.should_clarify(analysis)

                    if decision == ClarificationDecision.CLARIFY:
                        # Build validation errors context
                        error_context = "\n".join(f"  - {err}" for err in validation_t1.errors)

                        # Generate clarification question about validation failure
                        question = (
                            f"Your request could not be validated due to the following issues:\n\n"
                            f"{error_context}\n\n"
                            f"What would you like to do?"
                        )

                        if self.input_handler:
                            # Present options: simplify, rephrase, or cancel
                            choice = self.input_handler.prompt_choice(
                                question,
                                [
                                    "Simplify (make it simpler)",
                                    "Rephrase (provide more detail)",
                                    "Cancel",
                                ],
                            )

                            if choice and choice.lower() not in ["cancel", "3"]:
                                # Ask for clarified input
                                clarified_input = self.input_handler.prompt_user(
                                    "Please provide your clarification:"
                                )

                                if clarified_input:
                                    # Add user response to clarification manager
                                    self.clarification_manager.add_user_response(clarified_input)

                                    # Build context string with validation errors
                                    context = (
                                        f"Previous request failed validation with errors:\n{error_context}\n\n"
                                        f"User clarification: {clarified_input}"
                                    )

                                    self._logger.info(
                                        "Retrying with clarified input after Tier 1 validation failure"
                                    )

                                    # Recursive retry from sketch with clarified context
                                    return await self.plan(
                                        f"{context}\n\nOriginal: {user_input}",
                                        session,
                                        trace_id,
                                    )
                            else:
                                self._logger.warning("User cancelled after validation failure")

                return {
                    "status": "FAILED_VALIDATION_T1",
                    "errors": validation_t1.errors,
                    "total_latency_ms": (time.perf_counter() - total_start) * 1000,
                }

            # STAGE 3B: VALIDATE TIER 2 (input: FB bytes)
            validation_t2 = ValidationResult(valid=True, errors=[], tier=2, latency_ms=0)
            if self.validate_tier2._should_invoke(
                expanded_dict.get("steps", []), session, expanded_dict.get("complexity", "medium")
            ):
                self.metrics["arbiter_invocations"] += 1
                validation_t2 = await self.validate_tier2.check_safety(
                    expanded_bytes, session, trace_id
                )

                if not validation_t2.valid:
                    self.metrics["failed_validations"] += 1
                    viz.print_validation_result(
                        {
                            "valid": validation_t1.valid,
                            "errors": [],
                            "latency_ms": validation_t1.latency_ms,
                        },
                        {
                            "valid": False,
                            "errors": validation_t2.errors,
                            "latency_ms": validation_t2.latency_ms,
                        },
                    )

                    # M4 Epic 4.2: Clarification hook after Tier 2 validation failure
                    if self.enable_clarifications and self.clarification_manager:
                        from clarification_manager import ClarificationDecision

                        self._logger.warning(
                            f"Tier 2 (Arbiter) validation failed with {len(validation_t2.errors)} error(s). "
                            "Asking user for clarification..."
                        )

                        # Create analysis for Tier 2 failure (safety/policy issues)
                        analysis = IntentAnalysis(
                            intent=expanded_dict.get("intent", "unknown"),
                            confidence=0.4,  # Lower confidence for arbiter failures (safety concerns)
                            missing_entities=[],
                            original_query=user_input,
                        )

                        decision = self.clarification_manager.should_clarify(analysis)

                        if decision == ClarificationDecision.CLARIFY:
                            # Build validation errors context
                            error_context = "\n".join(f"  - {err}" for err in validation_t2.errors)

                            # Generate clarification question about safety/policy failure
                            question = (
                                f"Your request was reviewed by the arbiter and could not be approved "
                                f"due to safety or policy concerns:\n\n"
                                f"{error_context}\n\n"
                                f"What would you like to do?"
                            )

                            if self.input_handler:
                                # Present options: simplify, rephrase, or cancel
                                choice = self.input_handler.prompt_choice(
                                    question,
                                    [
                                        "Simplify (make it simpler)",
                                        "Rephrase (provide more detail)",
                                        "Cancel",
                                    ],
                                )

                                if choice and choice.lower() not in ["cancel", "3"]:
                                    # Ask for clarified input
                                    clarified_input = self.input_handler.prompt_user(
                                        "Please provide your clarification:"
                                    )

                                    if clarified_input:
                                        # Add user response to clarification manager
                                        self.clarification_manager.add_user_response(
                                            clarified_input
                                        )

                                        # Build context string with arbiter feedback
                                        context = (
                                            f"Previous request failed arbiter review with concerns:\n{error_context}\n\n"
                                            f"User clarification: {clarified_input}"
                                        )

                                        self._logger.info(
                                            "Retrying with clarified input after Tier 2 validation failure"
                                        )

                                        # Recursive retry from sketch with clarified context
                                        return await self.plan(
                                            f"{context}\n\nOriginal: {user_input}",
                                            session,
                                            trace_id,
                                        )
                                else:
                                    self._logger.warning("User cancelled after arbiter rejection")

                    return {
                        "status": "FAILED_VALIDATION_T2",
                        "errors": validation_t2.errors,
                        "total_latency_ms": (time.perf_counter() - total_start) * 1000,
                    }

            viz.print_validation_result(
                {"valid": True, "errors": [], "latency_ms": validation_t1.latency_ms},
                (
                    {"valid": True, "errors": [], "latency_ms": validation_t2.latency_ms}
                    if validation_t2.latency_ms > 0
                    else None
                ),
            )

            # STAGE 4: COMMIT (input: FB bytes)
            viz.print_stage_header(4, "COMMIT (Persistence)")
            total_latency_so_far = (time.perf_counter() - total_start) * 1000
            commit_result = await self.commit_stage.commit(
                expanded_bytes, session, trace_id, pipeline_latency_ms=total_latency_so_far
            )

            total_latency_ms = (time.perf_counter() - total_start) * 1000

            self.metrics["total_plans"] += 1
            self.metrics["successful_plans"] += 1

            # Get committed plan for size stats
            flowdef_bytes = self.commit_stage.committed_plans[commit_result.flow_id]["data"]

            # Print FlatBuffers stats
            viz.print_flatbuffer_stats(sketch_bytes, expanded_bytes, flowdef_bytes)

            # Print latency breakdown
            metrics = {
                "sketch_latency_ms": sketch_latency_ms,
                "expand_latency_ms": expand_latency_ms,
                "validate_t1_latency_ms": validation_t1.latency_ms,
                "validate_t2_latency_ms": validation_t2.latency_ms,
                "commit_latency_ms": commit_result.latency_ms,
                "total_latency_ms": total_latency_ms,
            }
            viz.print_latency_breakdown(metrics, slo_target_ms=2500)

            print(f"\n✅ Flow ID: {commit_result.flow_id}")
            print(f"   Status: {commit_result.status}")
            print(f"   Agents: {', '.join(expanded_dict.get('agents_required', []))}")

            return {
                "flow_id": commit_result.flow_id,
                "status": "COMMITTED",
                "intent": expanded_dict.get("intent", "N/A"),
                "steps_count": len(expanded_dict.get("steps", [])),
                "sketch_latency_ms": sketch_latency_ms,
                "expand_latency_ms": expand_latency_ms,
                "validate_t1_latency_ms": validation_t1.latency_ms,
                "validate_t2_latency_ms": validation_t2.latency_ms,
                "commit_latency_ms": commit_result.latency_ms,
                "total_latency_ms": total_latency_ms,
                "slo_pass": total_latency_ms < 2500,
            }

        except Exception as e:
            print(f"\n❌ ERROR: {e}")
            import traceback

            traceback.print_exc()
            return {
                "status": "ERROR",
                "error": str(e),
                "total_latency_ms": (time.perf_counter() - total_start) * 1000,
            }

    def print_metrics(self):
        """Print pipeline metrics"""
        print(f"\n{'='*70}")
        print("PIPELINE METRICS")
        print(f"{'='*70}")
        total = self.metrics["total_plans"]
        if total > 0:
            success_rate = (self.metrics["successful_plans"] / total) * 100
            print(f"Total Plans:             {total}")
            print(
                f"Successful:              {self.metrics['successful_plans']} ({success_rate:.1f}%)"
            )
            print(f"Failed Validations:      {self.metrics['failed_validations']}")
            print(f"Arbiter Invocations:     {self.metrics['arbiter_invocations']}")


# ============================================================================
# VISUALIZATION & METRICS DISPLAY
# ============================================================================


class VisualizationHelper:
    """Rich console visualization for pipeline execution"""

    @staticmethod
    def print_header(title: str):
        """Print section header"""
        print(f"\n{'='*80}")
        print(f"  {title}")
        print(f"{'='*80}")

    @staticmethod
    def print_stage_header(stage_num: int, stage_name: str):
        """Print stage header with box"""
        print(f"\n┌{'─'*78}┐")
        print(f"│ STAGE {stage_num}: {stage_name:<67}│")
        print(f"└{'─'*78}┘")

    @staticmethod
    def print_query_analysis(user_query: str, llm_response: str, parsed_plan: dict):
        """Show user query → LLM output → parsed plan"""
        print("\n📝 USER QUERY:")
        print(f'   "{user_query}"')

        print("\n🤖 LLM RAW OUTPUT:")
        # Truncate if too long
        display_response = llm_response[:300] + "..." if len(llm_response) > 300 else llm_response
        print(f"   {display_response}")

        print("\n✅ PARSED PLAN:")
        print(f"   Intent: {parsed_plan.get('intent', 'N/A')}")
        print(f"   Steps: {len(parsed_plan.get('steps', []))}")
        print(f"   Complexity: {parsed_plan.get('complexity', 'N/A')}")

    @staticmethod
    def print_plan_steps(steps: List[dict], show_details=True):
        """Visualize plan steps as flowchart"""
        print("\n📋 PLAN STEPS:")
        for i, step in enumerate(steps, 1):
            step_id = step.get("id", f"step_{i}")
            tool = step.get("tool", "N/A")
            agent = step.get("agent", "")
            desc = step.get("description", "")
            needs = step.get("needs", [])

            agent_str = f" → {agent}" if agent else ""
            print(f"   [{i}] {step_id}: {tool}{agent_str}")
            if show_details and desc:
                print(f"       └─ {desc}")
            if needs:
                print(f"       └─ Depends on: {', '.join(needs)}")

    @staticmethod
    def print_latency_breakdown(metrics: dict, slo_target_ms=2500):
        """Print latency metrics with SLO compliance"""
        print("\n⏱️  LATENCY BREAKDOWN:")
        print(f"   {'Stage':<20} {'Latency (ms)':>12} {'%':>8} {'SLO':>8}")
        print(f"   {'-'*20} {'-'*12} {'-'*8} {'-'*8}")

        total = metrics.get("total_latency_ms", 0)

        stages = [
            ("Sketch (LLM)", metrics.get("sketch_latency_ms", 0)),
            ("Expand (Lookup)", metrics.get("expand_latency_ms", 0)),
            ("Validate T1 (Rules)", metrics.get("validate_t1_latency_ms", 0)),
            ("Validate T2 (Arbiter)", metrics.get("validate_t2_latency_ms", 0)),
            ("Commit (Persist)", metrics.get("commit_latency_ms", 0)),
        ]

        for name, latency in stages:
            pct = (latency / total * 100) if total > 0 else 0
            print(f"   {name:<20} {latency:>10.2f}ms {pct:>7.1f}%")

        print(f"   {'-'*20} {'-'*12} {'-'*8} {'-'*8}")
        slo_status = "✅ PASS" if total < slo_target_ms else "❌ FAIL"
        print(f"   {'TOTAL':<20} {total:>10.2f}ms {100.0:>7.1f}% {slo_status:>8}")
        print(f"   {'SLO Target':<20} {slo_target_ms:>10.0f}ms")

    @staticmethod
    def print_validation_result(tier1: dict, tier2: dict = None):
        """Show validation results"""
        print("\n✓ VALIDATION:")

        # Tier 1
        status = "✅ PASS" if tier1.get("valid", False) else "❌ FAIL"
        print(f"   Tier 1 (Rules):  {status} ({tier1.get('latency_ms', 0):.2f}ms)")
        if tier1.get("errors"):
            for err in tier1["errors"]:
                print(f"      └─ ❌ {err}")

        # Tier 2
        if tier2 and tier2.get("latency_ms", 0) > 0:
            status = "✅ SAFE" if tier2.get("valid", False) else "❌ UNSAFE"
            print(f"   Tier 2 (Arbiter): {status} ({tier2.get('latency_ms', 0):.2f}ms)")
            if tier2.get("errors"):
                for err in tier2["errors"]:
                    print(f"      └─ ⚠️  {err}")
        else:
            print("   Tier 2 (Arbiter): ⏭️  SKIPPED (simple plan)")

    @staticmethod
    def print_flatbuffer_stats(sketch_bytes, expanded_bytes, flowdef_bytes):
        """Show FlatBuffers serialization stats"""
        print("\n💾 FLATBUFFERS SERIALIZATION:")
        print(f"   Sketch:        {len(sketch_bytes):>6} bytes")
        print(f"   ExpandedPlan:  {len(expanded_bytes):>6} bytes")
        print(f"   FlowDef:       {len(flowdef_bytes):>6} bytes")
        print(
            f"   TOTAL:         {len(sketch_bytes) + len(expanded_bytes) + len(flowdef_bytes):>6} bytes"
        )

    @staticmethod
    def print_sli_dashboard(all_results: List[dict]):
        """Print SLI/SLO dashboard for all tests"""
        print("\n" + "=" * 80)
        print("  📊 SLI/SLO DASHBOARD")
        print("=" * 80)

        total_tests = len(all_results)
        passed = sum(1 for r in all_results if r.get("slo_pass", False))
        failed = total_tests - passed

        latencies = [r.get("total_latency_ms", 0) for r in all_results]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        p50 = sorted(latencies)[len(latencies) // 2] if latencies else 0
        p95 = sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0
        p99 = sorted(latencies)[int(len(latencies) * 0.99)] if latencies else 0

        print(f"\n  Tests Executed:    {total_tests}")
        print(f"  SLO Compliance:    {passed}/{total_tests} ({100*passed/total_tests:.1f}%)")
        print(f"  Failed:            {failed}")

        print("\n  Latency Statistics:")
        print(f"    Average:         {avg_latency:>8.1f}ms")
        print(f"    P50 (median):    {p50:>8.1f}ms")
        print(
            f"    P95:             {p95:>8.1f}ms  {'✅' if p95 < 2500 else '❌'} (target: <2500ms)"
        )
        print(f"    P99:             {p99:>8.1f}ms")

        print("\n  Per-Stage Average Latencies:")
        sketch_avg = sum(r.get("sketch_latency_ms", 0) for r in all_results) / total_tests
        expand_avg = sum(r.get("expand_latency_ms", 0) for r in all_results) / total_tests
        validate_avg = (
            sum(r.get("validate_t1_latency_ms", 0) for r in all_results) / total_tests
            + sum(r.get("validate_t2_latency_ms", 0) for r in all_results) / total_tests
        )
        commit_avg = sum(r.get("commit_latency_ms", 0) for r in all_results) / total_tests

        print(f"    Sketch:          {sketch_avg:>8.1f}ms")
        print(f"    Expand:          {expand_avg:>8.1f}ms")
        print(f"    Validate:        {validate_avg:>8.1f}ms")
        print(f"    Commit:          {commit_avg:>8.1f}ms")


# ============================================================================
# MAIN TEST
# ============================================================================


async def main():
    """Run end-to-end planning pipeline test with rich visualization"""

    viz = VisualizationHelper()

    viz.print_header("🚀 K1 PLANNING PIPELINE POC - FlatBuffers Standard")

    # Get shared LLM provider (from poc root) - Use Groq for better performance
    print("\n⚙️  Initializing LLM Provider...")
    llm_provider = get_provider(prefer_local=False, max_workers=5)  # Use Groq, not local
    print(f"   Backend: {llm_provider.backend.value}")

    # Create pipeline (FlatBuffers only)
    print("   Creating pipeline with FlatBuffers serialization...")
    pipeline = PlanningPipeline(llm_provider, use_flatbuffers=True)

    # Create test session
    session = SessionFixture(session_id="test_001", band="AMBER")
    session.add_capability("READ_CALENDAR")
    session.add_capability("BOOK_RESERVATION")
    session.add_capability("SEND_MESSAGE")

    print(f"   Session Band: {session.band}")
    print(f"   Available Tools: {len(session.available_tools)}")
    print(f"   Available Capabilities: {len(session.available_caps)}")

    # Test cases
    test_cases = [
        "Book dinner with my wife at 7pm and check if it'll rain",
        "What time is my next meeting?",
        "Check the weather and show me restaurant options nearby",
    ]

    results = []

    for i, user_query in enumerate(test_cases, 1):
        viz.print_header(f"TEST CASE {i}/{len(test_cases)}")

        result = await pipeline.plan(user_query, session, trace_id=f"trace_{i:03d}")
        results.append(result)

        # Small delay between tests
        await asyncio.sleep(0.3)

    # Print final metrics
    pipeline.print_metrics()

    # Print comprehensive SLI dashboard
    viz.print_sli_dashboard(results)

    print("\n")


if __name__ == "__main__":
    asyncio.run(main())
