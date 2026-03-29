"""Concierge tool registry backed by real k1.SessionState.

Implements all 13 Concierge LLM tools from Section 10 of concierge.md:

  Signal (1):   acknowledge
  Cognitive (6): update_scoreboard, update_beliefs, update_clarifications,
                 update_narrative, refine_affect, promote_belief
  Read (3):     recall_memory, discover_capabilities, summarize_context
  Action (3):   invoke_capability, spawn_via_fabric, execute_workflow

Signal and Cognitive tools write to a REAL in-memory SessionState
(via k1.sessionstate.create_for_testing()).  Read and Action tools return
canned data from concierge_response_bank.py.

This registry satisfies the ToolRegistry protocol and can be used as a
drop-in replacement for CannedToolRegistry in the eval runners.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Callable, Dict, List, Optional

from core.models import ToolResult
from tools.concierge_response_bank import (
    get_capability_result,
    get_capability_results,
    get_memory_results,
    get_spawn_result,
    get_workflow_result,
)

# ---------------------------------------------------------------------------
# Tool definition (reuse the same shape as CannedToolRegistry)
# ---------------------------------------------------------------------------


class _ToolDef:
    """Registered tool with schema and handler."""

    __slots__ = ("name", "description", "parameters", "handler")

    def __init__(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        handler: Callable[..., Any],
    ):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.handler = handler

    def to_declaration(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


# ---------------------------------------------------------------------------
# SessionState wrapper -- lazy init to avoid import cost at module level
# ---------------------------------------------------------------------------

_session_manager: Any = None


def _get_session_manager() -> Any:
    """Create or return the shared in-memory SessionState manager."""
    global _session_manager
    if _session_manager is None:
        from k1.sessionstate import create_for_testing

        _session_manager = create_for_testing()
        _session_manager.start()
    return _session_manager


def reset_session_state() -> None:
    """Reset the global SessionState for a fresh benchmark run."""
    global _session_manager
    if _session_manager is not None:
        _session_manager.stop()
        _session_manager = None


# ---------------------------------------------------------------------------
# Concierge Tool Registry
# ---------------------------------------------------------------------------


class ConciergeToolRegistry:
    """
    Full 13-tool Concierge registry backed by real SessionState.

    Signal + Cognitive tools mutate a live in-memory SessionState via
    k1.sessionstate.  Read + Action tools return canned data so the
    PoC doesn't need Fabric or K0 Bridge running.

    State is shared across tool calls within a single benchmark run.
    Call reset_session_state() between runs.
    """

    def __init__(self) -> None:
        self._tools: Dict[str, _ToolDef] = {}
        self._call_counts: Dict[str, int] = {}
        self._ack_log: List[Dict[str, Any]] = []
        self._beliefs_promoted: List[str] = []
        self._register_all_tools()

    # ------------------------------------------------------------------
    # Protocol: ToolRegistry
    # ------------------------------------------------------------------

    def get_tool_declarations(self) -> List[Dict[str, Any]]:
        return [t.to_declaration() for t in self._tools.values()]

    async def execute(self, name: str, arguments: Dict[str, Any]) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(
                tool_name=name,
                ok=False,
                error_code="TOOL_NOT_FOUND",
                error_message=f"Unknown tool: {name}",
            )
        self._call_counts[name] = self._call_counts.get(name, 0) + 1
        try:
            result = tool.handler(**arguments)
            return ToolResult(tool_name=name, ok=True, output=result)
        except Exception as exc:
            return ToolResult(
                tool_name=name,
                ok=False,
                error_code="HANDLER_ERROR",
                error_message=str(exc),
            )

    def get_tool_names(self) -> List[str]:
        return list(self._tools.keys())

    def reset(self) -> None:
        """Reset tool state for a fresh run (satisfies ToolRegistry.reset)."""
        self._call_counts.clear()
        self._ack_log.clear()
        self._beliefs_promoted.clear()
        reset_session_state()

    # ------------------------------------------------------------------
    # Utility registration helper
    # ------------------------------------------------------------------

    def _reg(
        self,
        name: str,
        desc: str,
        parameters: Dict[str, Any],
        handler: Callable[..., Any],
    ) -> None:
        self._tools[name] = _ToolDef(name, desc, parameters, handler)

    # ------------------------------------------------------------------
    # Register all 13 tools
    # ------------------------------------------------------------------

    def _register_all_tools(self) -> None:
        # ---- SIGNAL (1) ----
        self._reg(
            "acknowledge",
            (
                "Emit intent confirmation to the user before any effectful work. "
                "MUST be the first tool called in iteration 1. "
                "Effectful tools without preceding acknowledge are REJECTED."
            ),
            {
                "type": "object",
                "properties": {
                    "ack_type": {
                        "type": "string",
                        "enum": ["commit", "progress", "closure"],
                        "description": (
                            "commit: state change happening; "
                            "progress: work starting; "
                            "closure: branch complete"
                        ),
                    },
                    "message": {
                        "type": "string",
                        "description": "User-facing confirmation text (max 150 tokens)",
                    },
                    "next_tool": {
                        "type": "string",
                        "description": (
                            "Name of the effectful tool to call next, or 'none' "
                            "for text-only responses"
                        ),
                    },
                },
                "required": ["ack_type", "message", "next_tool"],
            },
            self._handle_acknowledge,
        )

        # ---- COGNITIVE (6) ----
        self._reg(
            "update_scoreboard",
            (
                "Update task tracking, referent resolution, salience map, "
                "and topic stack in the scoreboard (6KB budget). "
                "Supports: add_referent, set, push_topic, set_salience."
            ),
            {
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": [
                            "add_referent",
                            "set_task",
                            "update_progress",
                            "push_topic",
                            "set_salience",
                            "set_intent",
                        ],
                        "description": "Scoreboard operation to perform",
                    },
                    "task_name": {"type": "string", "description": "Task name (for set_task)"},
                    "task_status": {
                        "type": "string",
                        "enum": ["pending", "in_progress", "completed", "failed"],
                        "description": "Task status",
                    },
                    "progress_pct": {"type": "number", "description": "Progress 0-100"},
                    "referent_text": {
                        "type": "string",
                        "description": "Referent text (for add_referent)",
                    },
                    "entity_id": {"type": "string", "description": "Entity ID"},
                    "entity_type": {
                        "type": "string",
                        "description": "Entity type (person, place, etc.)",
                    },
                    "topic": {"type": "string", "description": "Topic name (for push_topic)"},
                    "salience": {"type": "number", "description": "Salience score 0.0-1.0"},
                    "intent": {"type": "string", "description": "User intent (for set_intent)"},
                },
                "required": ["operation"],
            },
            self._handle_update_scoreboard,
        )

        self._reg(
            "update_beliefs",
            (
                "Maintain family knowledge graph in beliefs_active (8KB budget). "
                "Add facts, correct facts, record preferences as subject-predicate-object triples. "
                "REQUIRES entity_id from resolve_entity -- raw names are REJECTED."
            ),
            {
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["add_fact", "correct_fact", "add_preference"],
                        "description": "Belief operation",
                    },
                    "entity_id": {
                        "type": "string",
                        "description": (
                            "Stable entity ID from resolve_entity (e.g., 'person:Mom:a1b2c3d4'). "
                            "REQUIRED -- call resolve_entity first to obtain this."
                        ),
                    },
                    "entity_type": {
                        "type": "string",
                        "description": "Entity kind: person, event, place, concept",
                    },
                    "subject": {
                        "type": "string",
                        "description": "DEPRECATED legacy entity name -- use entity_id instead",
                    },
                    "predicate": {"type": "string", "description": "Relationship (e.g., 'diet')"},
                    "object_value": {"type": "string", "description": "Value (e.g., 'vegan')"},
                    "confidence": {
                        "type": "number",
                        "description": "Confidence 0.0-1.0 (default 0.8)",
                    },
                    "source": {
                        "type": "string",
                        "enum": ["user_stated", "inferred", "tool_result"],
                        "description": "How this belief was learned",
                    },
                },
                "required": ["operation", "predicate", "object_value"],
            },
            self._handle_update_beliefs,
        )

        self._reg(
            "update_clarifications",
            (
                "Track clarification gaps and resolutions (4KB budget). "
                "Record when information is missing and when gaps are resolved."
            ),
            {
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["record_gap", "resolve_gap", "expire_gap"],
                        "description": "Clarification operation",
                    },
                    "gap_type": {
                        "type": "string",
                        "enum": [
                            "ENTITY_MISSING",
                            "TIME_AMBIGUOUS",
                            "REFERENCE_UNRESOLVED",
                            "INTENT_AMBIGUOUS",
                            "CONSTRAINT_UNCLEAR",
                        ],
                        "description": "Type of information gap",
                    },
                    "description": {"type": "string", "description": "Gap description"},
                    "gap_id": {"type": "string", "description": "Gap ID (for resolve/expire)"},
                    "resolution": {"type": "string", "description": "Gap resolution text"},
                },
                "required": ["operation"],
            },
            self._handle_update_clarifications,
        )

        self._reg(
            "update_narrative",
            (
                "Manage conversation threads (4KB budget). "
                "Create, switch, pause, resolve threads to track discourse structure."
            ),
            {
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": [
                            "new_thread",
                            "switch_thread",
                            "resume_thread",
                            "continue_thread",
                            "close_thread",
                        ],
                        "description": "Thread operation",
                    },
                    "thread_id": {
                        "type": "string",
                        "description": "Thread ID (for switch/resume/close)",
                    },
                    "topic": {"type": "string", "description": "Thread topic (for new_thread)"},
                    "goal": {"type": "string", "description": "Thread goal"},
                    "domains": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Domain tags",
                    },
                },
                "required": ["operation"],
            },
            self._handle_update_narrative,
        )

        self._reg(
            "refine_affect",
            (
                "Override Phase 1 emotion classification when the LLM detects "
                "emotional nuance (sarcasm, mixed signals) that the classifier missed. "
                "Rare tool -- only for genuine disagreements with UltraBERT."
            ),
            {
                "type": "object",
                "properties": {
                    "override_emotion": {
                        "type": "string",
                        "description": "Corrected primary emotion (Plutchik taxonomy)",
                    },
                    "override_intensity": {
                        "type": "number",
                        "description": "Corrected intensity 0.0-1.0",
                    },
                    "override_valence": {
                        "type": "string",
                        "enum": ["positive", "negative", "neutral", "mixed"],
                        "description": "Corrected valence direction",
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "Why the LLM disagrees with classifier",
                    },
                },
                "required": [
                    "override_emotion",
                    "override_intensity",
                    "override_valence",
                    "reasoning",
                ],
            },
            self._handle_refine_affect,
        )

        self._reg(
            "promote_belief",
            (
                "Promote a belief across storage tiers. "
                "warm_to_hot: copy from WARM to HOT. "
                "hot_to_k0: persist to K0 long-term memory via Bridge."
            ),
            {
                "type": "object",
                "properties": {
                    "belief_id": {"type": "string", "description": "UUID of belief to promote"},
                    "direction": {
                        "type": "string",
                        "enum": ["warm_to_hot", "hot_to_k0"],
                        "description": "Promotion direction",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Why this belief is being promoted",
                    },
                },
                "required": ["belief_id", "direction"],
            },
            self._handle_promote_belief,
        )

        # ---- READ (4) ----
        self._reg(
            "resolve_entity",
            (
                "Resolve a human-readable entity name to a stable entity_id. "
                "MUST be called before update_beliefs to obtain the entity_id. "
                "Searches scoreboard referents first; creates a new referent if not found."
            ),
            {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Human-readable entity name (e.g., 'Mom', 'Jake', 'birthday dinner')",
                    },
                    "entity_type": {
                        "type": "string",
                        "description": "Type hint: person, event, place, concept (helps disambiguation)",
                    },
                },
                "required": ["name"],
            },
            self._handle_resolve_entity,
        )

        self._reg(
            "recall_memory",
            (
                "Query K0 long-term memory for facts, beliefs, conversation "
                "summaries, and relationships. Returns ranked results by relevance."
            ),
            {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language query for semantic search",
                    },
                    "selectors": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Memory categories: beliefs, conversations, events, relationships, preferences",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum results (default 5, max 20)",
                    },
                },
                "required": ["query"],
            },
            self._handle_recall_memory,
        )

        self._reg(
            "discover_capabilities",
            (
                "Search Fabric Capability Registry for available tools, agents, "
                "and workflows. Returns scored and ranked results."
            ),
            {
                "type": "object",
                "properties": {
                    "intent": {
                        "type": "string",
                        "description": "What the user wants to do",
                    },
                    "domain": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Domain tags to filter by. Valid domains: "
                            "DINING, LIFESTYLE, HEALTH, SCHEDULING, FAMILY, GIFTING"
                        ),
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of top results (default 10)",
                    },
                },
                "required": ["intent", "domain"],
            },
            self._handle_discover_capabilities,
        )

        self._reg(
            "summarize_context",
            (
                "Generate a compressed summary of current SessionState for "
                "token budget management. Used when context exceeds 80%% of window."
            ),
            {
                "type": "object",
                "properties": {
                    "sections": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Sections to summarize (default: all HOT)",
                    },
                    "strategy": {
                        "type": "string",
                        "enum": ["extractive", "abstractive", "hybrid"],
                        "description": "Summarization approach",
                    },
                    "target_tokens": {
                        "type": "integer",
                        "description": "Target output token count",
                    },
                },
                "required": [],
            },
            self._handle_summarize_context,
        )

        # ---- ACTION (3) ----
        self._reg(
            "invoke_capability",
            (
                "Execute a single Fabric capability by name. "
                "Used for restaurant search, booking, menu lookup, etc."
            ),
            {
                "type": "object",
                "properties": {
                    "capability": {
                        "type": "string",
                        "description": "Canonical capability name (e.g., 'tool.execute.restaurant_search')",
                    },
                    "params": {
                        "type": "object",
                        "description": "Parameters for the capability",
                    },
                    "timeout_ms": {
                        "type": "integer",
                        "description": "Per-call timeout (default 30s)",
                    },
                },
                "required": ["capability", "params"],
            },
            self._handle_invoke_capability,
        )

        self._reg(
            "spawn_via_fabric",
            (
                "Create a dynamic agent via Fabric. "
                "The agent is registered and can be invoked later. "
                "AMBER band minimum. Agents inherit creator's safety band."
            ),
            {
                "type": "object",
                "properties": {
                    "agent_name": {
                        "type": "string",
                        "description": "Agent name (pattern: agent.execute.<identifier>)",
                    },
                    "description": {
                        "type": "string",
                        "description": "Agent purpose description",
                    },
                    "domain": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Domain tags (non-empty)",
                    },
                    "tools_granted": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tools the agent can use",
                    },
                    "llm_budget_tokens": {
                        "type": "integer",
                        "description": "Token budget for the agent (512-32768)",
                    },
                },
                "required": ["agent_name", "description", "domain", "tools_granted"],
            },
            self._handle_spawn_via_fabric,
        )

        self._reg(
            "execute_workflow",
            (
                "Execute a workflow via Orchestrator. Returns immediately with "
                "'queued' status. Results arrive asynchronously via Delta Bus."
            ),
            {
                "type": "object",
                "properties": {
                    "workflow_id": {
                        "type": "string",
                        "description": "Workflow identifier (e.g., 'workflow.birthday_party_planning')",
                    },
                    "params": {
                        "type": "object",
                        "description": "Workflow input parameters",
                    },
                    "timeout_ms": {
                        "type": "integer",
                        "description": "Overall workflow timeout",
                    },
                },
                "required": ["workflow_id", "params"],
            },
            self._handle_execute_workflow,
        )

        # ---- final_answer (meta) ----
        self._reg(
            "final_answer",
            "Provide the final answer to the user. Call this when your task is complete.",
            {
                "type": "object",
                "properties": {
                    "answer": {"type": "string", "description": "The complete answer to present"},
                },
                "required": ["answer"],
            },
            self._handle_final_answer,
        )

        # ---- spawn_agent (meta -- intercepted by SmartReactRunner) ----
        self._reg(
            "spawn_agent",
            (
                "Delegate a complex sub-task to a specialized sub-agent. "
                "The sub-agent runs its own ReAct loop with an independent tool budget "
                "and returns structured findings. Use when a sub-task needs >3 tool calls "
                "(e.g., detailed menu analysis, booking coordination, multi-venue comparison). "
                "The sub-agent inherits your available tools."
            ),
            {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "Clear, specific description of the sub-task to delegate",
                    },
                    "tool_budget": {
                        "type": "integer",
                        "description": "Maximum tool calls the sub-agent may use (default: 5)",
                    },
                },
                "required": ["task"],
            },
            lambda **kwargs: {"status": "delegated", "task": kwargs.get("task", "")},
        )

    # ==================================================================
    # SIGNAL handlers
    # ==================================================================

    def _handle_acknowledge(
        self,
        ack_type: str = "progress",
        message: str = "",
        next_tool: str = "none",
    ) -> Dict[str, Any]:
        entry = {
            "ack_type": ack_type,
            "message": message,
            "next_tool": next_tool,
            "displayed": True,
            "display_latency_ms": 45,
            "timestamp_ms": int(time.time() * 1000),
        }
        self._ack_log.append(entry)
        return {
            "displayed": True,
            "formatted_message": message,
            "display_latency_ms": 45,
        }

    # ==================================================================
    # COGNITIVE handlers
    # ==================================================================

    def _handle_update_scoreboard(
        self,
        operation: str = "set_task",
        task_name: str = "",
        task_status: str = "in_progress",
        progress_pct: float = 0.0,
        referent_text: str = "",
        entity_id: str = "",
        entity_type: str = "",
        topic: str = "",
        salience: float = 0.5,
        intent: str = "",
    ) -> Dict[str, Any]:
        mgr = _get_session_manager()

        if operation == "add_referent":
            r = mgr.mutate(
                "scoreboard",
                "add_referent",
                {
                    "text": referent_text or entity_id,
                    "entity_id": entity_id,
                    "entity_type": entity_type,
                },
            )
        elif operation == "set_task":
            r = mgr.mutate(
                "scoreboard",
                "set",
                {
                    "key": f"task_{task_name}",
                    "value": {"name": task_name, "status": task_status, "progress": progress_pct},
                },
            )
        elif operation == "update_progress":
            r = mgr.mutate(
                "scoreboard",
                "set",
                {
                    "key": f"task_{task_name}",
                    "value": {"name": task_name, "status": task_status, "progress": progress_pct},
                },
            )
        elif operation == "push_topic":
            r = mgr.mutate(
                "scoreboard",
                "set",
                {"key": f"topic_{topic}", "value": {"name": topic, "salience": salience}},
            )
        elif operation == "set_salience":
            r = mgr.mutate("scoreboard", "set", {"key": f"salience_{entity_id}", "value": salience})
        elif operation == "set_intent":
            r = mgr.mutate("scoreboard", "set", {"key": "user_intent", "value": intent})
        else:
            return {"success": False, "error": f"Unknown operation: {operation}"}

        section = mgr.get_section("scoreboard")
        return {
            "success": r.success,
            "section_bytes": r.new_size_bytes or section.get_size_bytes(),
            "available_bytes": max(0, 6144 - (r.new_size_bytes or section.get_size_bytes())),
            "operation": operation,
        }

    def _handle_update_beliefs(
        self,
        operation: str = "add_fact",
        entity_id: str = "",
        entity_type: str = "",
        subject: str = "",
        predicate: str = "",
        object_value: str = "",
        confidence: float = 0.8,
        source: str = "user_stated",
    ) -> Dict[str, Any]:
        # Strict mode: entity_id required, raw subject names REJECTED
        if not entity_id:
            if subject:
                return {
                    "success": False,
                    "error": (
                        f"update_beliefs requires entity_id; raw subject '{subject}' rejected. "
                        "Call resolve_entity(name='{subject}') first to obtain a stable entity_id."
                    ),
                    "hint": "resolve_entity",
                }
            return {
                "success": False,
                "error": "entity_id is required. Call resolve_entity first.",
                "hint": "resolve_entity",
            }

        # Use entity_id as the canonical subject for storage
        canonical_subject = entity_id

        mgr = _get_session_manager()
        src_map = {
            "user_stated": "user_stated",
            "inferred": "inferred",
            "tool_result": "tool_result",
        }

        r = mgr.mutate(
            "beliefs_active",
            "add_fact",
            {
                "subject": canonical_subject,
                "predicate": predicate,
                "obj": object_value,
                "confidence": confidence,
                "source": src_map.get(source, source),
            },
        )

        section = mgr.get_section("beliefs_active")
        # Find the belief ID for the just-added fact
        belief_id = ""
        if r.success:
            facts = section.list_facts()
            for f in facts:
                if (
                    f.subject == canonical_subject
                    and f.predicate == predicate
                    and f.object == object_value
                ):
                    belief_id = f.id
                    break

        return {
            "success": r.success,
            "belief_id": belief_id or str(uuid.uuid4()),
            "entity_id": entity_id,
            "is_correction": operation == "correct_fact",
            "section_bytes": r.new_size_bytes or section.get_size_bytes(),
            "error": r.error,
        }

    def _handle_update_clarifications(
        self,
        operation: str = "record_gap",
        gap_type: str = "CONSTRAINT_UNCLEAR",
        description: str = "",
        gap_id: str = "",
        resolution: str = "",
    ) -> Dict[str, Any]:
        mgr = _get_session_manager()

        if operation == "record_gap":
            r = mgr.mutate(
                "clarifications",
                "request",
                {
                    "agent_id": "concierge",
                    "question": f"[{gap_type}] {description}",
                    "priority": 1,
                },
            )
            section = mgr.get_section("clarifications")
            pending = section.get_pending() if hasattr(section, "get_pending") else []
            return {
                "success": r.success,
                "gap_id": gap_id or str(uuid.uuid4()),
                "open_gaps_count": len(pending),
            }
        elif operation == "resolve_gap":
            # Use answer if we have a gap_id
            if gap_id:
                r = mgr.mutate(
                    "clarifications",
                    "answer",
                    {"clarification_id": gap_id, "answer": resolution},
                )
            else:
                r = mgr.mutate(
                    "clarifications", "set", {"key": f"resolved_{gap_id}", "value": resolution}
                )
            return {
                "success": r.success if hasattr(r, "success") else True,
                "gap_id": gap_id,
                "open_gaps_count": 0,
            }
        elif operation == "expire_gap":
            r = mgr.mutate("clarifications", "set", {"key": f"expired_{gap_id}", "value": True})
            return {"success": True, "gap_id": gap_id, "open_gaps_count": 0}

        return {"success": False, "error": f"Unknown operation: {operation}"}

    def _handle_update_narrative(
        self,
        operation: str = "new_thread",
        thread_id: str = "",
        topic: str = "",
        goal: str = "",
        domains: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        mgr = _get_session_manager()

        if operation == "new_thread":
            r = mgr.mutate(
                "narrative_active",
                "create_thread",
                {"title": topic, "goal": goal or topic},
            )
            section = mgr.get_section("narrative_active")
            threads = section.get_all_threads()
            # Get the thread ID of the most recently created thread
            new_thread_id = threads[-1].id if threads else str(uuid.uuid4())
            return {
                "success": r.success,
                "thread_id": new_thread_id,
                "active_threads": len(section.get_active_threads()),
                "thread_status": "ACTIVE",
            }
        elif operation == "close_thread":
            r = mgr.mutate("narrative_active", "resolve_thread", {"thread_id": thread_id})
            return {
                "success": r.success,
                "thread_id": thread_id,
                "active_threads": 0,
                "thread_status": "RESOLVED",
            }
        elif operation == "switch_thread":
            r = mgr.mutate("narrative_active", "switch_to", {"thread_id": thread_id})
            return {
                "success": r.success,
                "thread_id": thread_id,
                "active_threads": 1,
                "thread_status": "ACTIVE",
            }
        elif operation == "resume_thread":
            r = mgr.mutate("narrative_active", "switch_to", {"thread_id": thread_id})
            return {
                "success": r.success,
                "thread_id": thread_id,
                "active_threads": 1,
                "thread_status": "ACTIVE",
            }
        elif operation == "continue_thread":
            return {
                "success": True,
                "thread_id": thread_id,
                "active_threads": 1,
                "thread_status": "ACTIVE",
            }

        return {"success": False, "error": f"Unknown operation: {operation}"}

    def _handle_refine_affect(
        self,
        override_emotion: str = "",
        override_intensity: float = 0.5,
        override_valence: str = "neutral",
        reasoning: str = "",
    ) -> Dict[str, Any]:
        mgr = _get_session_manager()

        # Read current before override
        section = mgr.get_section("affective_now")
        prev_emotion = "neutral"
        prev_intensity = 0.0
        history = (
            section.get_emotion_history(n=1) if hasattr(section, "get_emotion_history") else []
        )
        if history:
            prev_emotion = history[0].emotion if hasattr(history[0], "emotion") else "neutral"
            prev_intensity = history[0].intensity if hasattr(history[0], "intensity") else 0.0

        # Map valence string to numeric
        valence_map = {"positive": 0.8, "negative": -0.6, "neutral": 0.0, "mixed": 0.2}
        valence_num = valence_map.get(override_valence, 0.0)

        r = mgr.mutate(
            "affective_now",
            "update",
            {
                "emotion": override_emotion,
                "intensity": override_intensity,
                "valence": valence_num,
                "arousal": override_intensity,
                "source": "llm_override",
            },
        )

        return {
            "success": r.success,
            "previous_emotion": prev_emotion,
            "previous_intensity": prev_intensity,
            "override_applied": r.success,
            "reasoning": reasoning,
        }

    def _handle_promote_belief(
        self,
        belief_id: str = "",
        direction: str = "hot_to_k0",
        reason: str = "",
    ) -> Dict[str, Any]:
        self._beliefs_promoted.append(belief_id)

        if direction == "hot_to_k0":
            k0_receipt = f"k0-receipt-{uuid.uuid4().hex[:8]}"
            return {
                "success": True,
                "belief_id": belief_id,
                "destination": "k0",
                "k0_store_receipt": k0_receipt,
            }
        elif direction == "warm_to_hot":
            return {
                "success": True,
                "belief_id": belief_id,
                "destination": "beliefs_active",
                "k0_store_receipt": None,
            }
        return {"success": False, "error": f"Unknown direction: {direction}"}

    # ==================================================================
    # READ handlers
    # ==================================================================

    def _handle_resolve_entity(
        self,
        name: str = "",
        entity_type: str = "",
    ) -> Dict[str, Any]:
        """Resolve a human-readable name to a stable entity_id.

        Searches scoreboard referents first (case-insensitive match).
        If not found, creates a new referent with a namespaced ID.
        """
        if not name:
            return {
                "found": False,
                "error": "name is required",
                "entity_id": "",
                "canonical_name": "",
                "entity_type": entity_type or "unknown",
                "confidence": 0.0,
            }

        mgr = _get_session_manager()
        sb = mgr.get_section("scoreboard")
        referents = sb.list_referents() if hasattr(sb, "list_referents") else []

        # Try match by text (case-insensitive)
        name_lower = name.strip().lower()
        for r in referents:
            r_text = (r.text or "").strip().lower()
            r_eid = (r.entity_id or "").strip().lower()
            if r_text == name_lower or r_eid == name_lower:
                return {
                    "found": True,
                    "entity_id": r.entity_id or r.text,
                    "canonical_name": r.text,
                    "entity_type": entity_type or getattr(r, "entity_type", "unknown") or "unknown",
                    "confidence": 0.95,
                }

        # Not found -- create referent with namespaced ID
        etype = entity_type or "entity"
        new_id = f"{etype}:{name}:{uuid.uuid4().hex[:8]}"

        mgr.mutate(
            "scoreboard",
            "add_referent",
            {"text": name, "entity_id": new_id, "entity_type": etype},
        )

        return {
            "found": False,
            "entity_id": new_id,
            "canonical_name": name,
            "entity_type": etype,
            "confidence": 0.6,
        }

    def _handle_recall_memory(
        self,
        query: str = "",
        selectors: Optional[List[str]] = None,
        max_results: int = 5,
    ) -> Dict[str, Any]:
        results = get_memory_results(query, selectors)
        if max_results < len(results.get("results", [])):
            results["results"] = results["results"][:max_results]
        return results

    def _handle_discover_capabilities(
        self,
        intent: str = "",
        domain: Optional[List[str]] = None,
        top_k: int = 10,
    ) -> Dict[str, Any]:
        return get_capability_results(intent, domain or [], top_k)

    def _handle_summarize_context(
        self,
        sections: Optional[List[str]] = None,
        strategy: str = "hybrid",
        target_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        mgr = _get_session_manager()
        hot_sections = sections or [
            "control",
            "beliefs_active",
            "scoreboard",
            "history_active",
            "clarifications",
            "affective_now",
            "narrative_active",
            "meta",
        ]

        # Read all HOT sections and build a comprehensive state summary
        section_data: Dict[str, Any] = {}
        total_bytes = 0
        for name in hot_sections:
            try:
                sec = mgr.get_section(name)
                size = sec.get_size_bytes()
                total_bytes += size
                if name == "beliefs_active":
                    facts = sec.list_facts()
                    section_data[name] = {
                        "fact_count": len(facts),
                        "facts": [
                            {
                                "subject": f.subject,
                                "predicate": f.predicate,
                                "object": f.object,
                                "confidence": f.confidence,
                            }
                            for f in facts
                        ],
                        "size_bytes": size,
                    }
                elif name == "scoreboard":
                    referents = sec.list_referents()
                    section_data[name] = {
                        "referent_count": len(referents),
                        "referents": [
                            {"text": r.text, "entity_id": r.entity_id} for r in referents
                        ],
                        "size_bytes": size,
                    }
                elif name == "narrative_active":
                    threads = sec.get_all_threads()
                    section_data[name] = {
                        "thread_count": len(threads),
                        "threads": [
                            {"id": t.id, "title": t.title, "state": str(t.state)} for t in threads
                        ],
                        "size_bytes": size,
                    }
                elif name == "clarifications":
                    pending = sec.get_pending() if hasattr(sec, "get_pending") else []
                    section_data[name] = {
                        "pending_count": len(pending),
                        "size_bytes": size,
                    }
                else:
                    section_data[name] = {"size_bytes": size}
            except Exception:
                section_data[name] = {"error": "section not available"}

        # Build summary text
        summary_parts = []
        for name, data in section_data.items():
            if name == "beliefs_active" and "facts" in data:
                for f in data["facts"]:
                    summary_parts.append(f"{f['subject']} {f['predicate']} {f['object']}")
            elif name == "narrative_active" and "threads" in data:
                for t in data["threads"]:
                    summary_parts.append(f"Thread: {t['title']} ({t['state']})")
        summary_text = "; ".join(summary_parts) if summary_parts else "Empty session state."

        original_tokens = total_bytes // 4
        summary_tokens = len(summary_text) // 4

        return {
            "summary": summary_text,
            "original_tokens": original_tokens,
            "summary_tokens": summary_tokens,
            "compression_ratio": round(summary_tokens / max(original_tokens, 1), 3),
            "sections_included": list(section_data.keys()),
            "sections_dropped": [],
            "strategy_used": strategy,
            "section_details": section_data,
        }

    # ==================================================================
    # ACTION handlers
    # ==================================================================

    def _handle_invoke_capability(
        self,
        capability: str = "",
        params: Optional[Dict[str, Any]] = None,
        timeout_ms: int = 30000,
    ) -> Dict[str, Any]:
        return get_capability_result(capability, params or {})

    def _handle_spawn_via_fabric(
        self,
        agent_name: str = "",
        description: str = "",
        domain: Optional[List[str]] = None,
        tools_granted: Optional[List[str]] = None,
        llm_budget_tokens: int = 4096,
    ) -> Dict[str, Any]:
        return get_spawn_result(
            agent_name,
            tools_granted=tools_granted or [],
            llm_budget_tokens=llm_budget_tokens,
        )

    def _handle_execute_workflow(
        self,
        workflow_id: str = "",
        params: Optional[Dict[str, Any]] = None,
        timeout_ms: int = 60000,
    ) -> Dict[str, Any]:
        return get_workflow_result(workflow_id, params or {})

    def _handle_final_answer(self, answer: str = "") -> Dict[str, Any]:
        return {"answer": answer, "complete": True}
