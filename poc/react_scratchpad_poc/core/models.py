"""
Core data models for the ReactLoopScratchpad PoC.

Two memory paradigms compared:
  - Naive: linear message list, no compaction, no budget, no structured findings
  - Smart: managed scratchpad with structured findings, LLM compaction, budget, sub-agents

Architecture source: k1/concierge/concierge.md Section 7.5 (ADR-0098)
"""

from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Tier(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class SubAgentStatus(str, Enum):
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Budget
# ---------------------------------------------------------------------------


class LoopBudget(BaseModel):
    """Tiered resource budget for a ReAct loop execution."""

    max_tools: int = 10
    max_iterations: int = 10
    timeout_ms: int = 10_000
    max_context_tokens: int = 128_000
    max_tokens_out: int = 2_000

    # mutable counters
    tools_used: int = 0
    iterations_used: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    elapsed_ms: int = 0

    @classmethod
    def for_tier(cls, tier: Tier) -> "LoopBudget":
        presets = {
            Tier.LOW: dict(max_tools=6, max_iterations=6, timeout_ms=2_000, max_tokens_out=500),
            Tier.MEDIUM: dict(
                max_tools=10, max_iterations=10, timeout_ms=10_000, max_tokens_out=2_000
            ),
            Tier.HIGH: dict(
                max_tools=15, max_iterations=15, timeout_ms=45_000, max_tokens_out=8_000
            ),
        }
        return cls(**presets[tier])

    @property
    def exhausted(self) -> bool:
        return (
            self.tools_used >= self.max_tools
            or self.iterations_used >= self.max_iterations
            or self.elapsed_ms >= self.timeout_ms
        )

    @property
    def remaining_tools(self) -> int:
        return max(0, self.max_tools - self.tools_used)

    @property
    def remaining_iterations(self) -> int:
        return max(0, self.max_iterations - self.iterations_used)

    def slice(self, tool_budget: int) -> "LoopBudget":
        """Create a child budget slice for a sub-agent."""
        available = self.remaining_tools
        granted = min(tool_budget, available)
        return LoopBudget(
            max_tools=granted,
            max_iterations=granted + 2,  # slight headroom for reasoning
            timeout_ms=self.timeout_ms,
            max_context_tokens=self.max_context_tokens,
            max_tokens_out=self.max_tokens_out,
        )

    def consume_tool(self) -> None:
        self.tools_used += 1

    def consume_iteration(self) -> None:
        self.iterations_used += 1

    def add_tokens(self, tokens_in: int, tokens_out: int) -> None:
        self.tokens_in += tokens_in
        self.tokens_out += tokens_out

    def return_unused(self, child: "LoopBudget") -> None:
        """Return unused tool calls from a child budget back to parent."""
        returned = child.remaining_tools
        self.tools_used = max(0, self.tools_used - returned)


# ---------------------------------------------------------------------------
# Structured Finding
# ---------------------------------------------------------------------------


class Finding(BaseModel):
    """A structured fact extracted from a tool result."""

    key: str
    value: Any
    type: str = "fact"  # weather, flight, fact, calculation, error, etc.
    confidence: float = 1.0
    source_iteration: int = 0
    source_tool: str = ""


# ---------------------------------------------------------------------------
# Failed Attempt
# ---------------------------------------------------------------------------


class FailedAttempt(BaseModel):
    """Record of a failed tool call for recovery tracking."""

    tool_name: str
    error_code: str = "UNKNOWN"
    error_message: str = ""
    iteration: int = 0
    arguments: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Sub-Agent Record
# ---------------------------------------------------------------------------


class SubAgentRecord(BaseModel):
    """Tracks a spawned sub-agent and its lifecycle."""

    agent_id: str = Field(default_factory=lambda: f"agent-{uuid.uuid4().hex[:8]}")
    task: str = ""
    status: SubAgentStatus = SubAgentStatus.RUNNING
    findings: List[Finding] = Field(default_factory=list)
    budget_consumed: Optional[LoopBudget] = None
    result: Optional[str] = None
    depth: int = 1
    parent_id: Optional[str] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Cognitive Write (audit trail)
# ---------------------------------------------------------------------------


class CognitiveWrite(BaseModel):
    """Records a mutation to session state for audit."""

    section: str
    operation: str  # set, append, delete
    key: str
    old_value: Any = None
    new_value: Any = None
    iteration: int = 0


# ---------------------------------------------------------------------------
# Iteration Snapshot
# ---------------------------------------------------------------------------


class IterationSnapshot(BaseModel):
    """Debug snapshot captured at end of each iteration."""

    iteration: int
    thought: Optional[str] = None
    action: Optional[str] = None
    observation_summary: Optional[str] = None
    tokens_in: int = 0
    tokens_out: int = 0
    duration_ms: int = 0
    context_size_tokens: int = 0
    findings_count: int = 0
    messages_count: int = 0
    compacted: bool = False
    tools_called: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Message (simplified)
# ---------------------------------------------------------------------------


class Message(BaseModel):
    """A message in the conversation for LLM context."""

    role: str  # system, user, assistant, tool
    content: str
    tool_call_id: Optional[str] = None
    tool_name: Optional[str] = None
    is_compacted_summary: bool = False


# ---------------------------------------------------------------------------
# Tool Call & Tool Result
# ---------------------------------------------------------------------------


class ToolCall(BaseModel):
    call_id: str = Field(default_factory=lambda: f"call-{uuid.uuid4().hex[:8]}")
    name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    tool_name: str
    call_id: str = ""
    ok: bool = True
    output: Any = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


# ---------------------------------------------------------------------------
# Turn Record (per-iteration log for eval)
# ---------------------------------------------------------------------------


class TurnRecord(BaseModel):
    iteration: int
    assistant_message: Optional[str] = None
    tool_calls: List[ToolCall] = Field(default_factory=list)
    tool_results: List[ToolResult] = Field(default_factory=list)
    context_tokens_estimate: int = 0
    findings_snapshot: Dict[str, Any] = Field(default_factory=dict)
    final_answer_fragment: Optional[str] = None


# ---------------------------------------------------------------------------
# Run Result (output of a single scenario run)
# ---------------------------------------------------------------------------


class RunResult(BaseModel):
    runner_name: str  # "naive_react" or "smart_react"
    scenario_id: str
    success: bool = False
    final_answer: Optional[str] = None
    turns: List[TurnRecord] = Field(default_factory=list)
    metrics: Dict[str, Any] = Field(default_factory=dict)
    errors: List[str] = Field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""

    # Smart-only metrics
    total_compactions: int = 0
    total_findings: int = 0
    total_sub_agents: int = 0
    max_nesting_depth: int = 0
    budget_overspend: bool = False


# ---------------------------------------------------------------------------
# Scratchpad (the core innovation)
# ---------------------------------------------------------------------------


class Scratchpad(BaseModel):
    """
    Ephemeral working memory for a single ReAct loop execution.

    Unlike naive message passing (append everything), the scratchpad:
    - Extracts structured findings from tool results
    - Compacts older messages via LLM summarization
    - Tracks budget and prevents overspend
    - Manages sub-agent hierarchies
    - Records failures for recovery
    - Maintains a cognitive write audit trail

    Created at loop start, destroyed at loop end. Never persisted.
    """

    turn_id: str = Field(default_factory=lambda: f"turn-{uuid.uuid4().hex[:8]}")
    system_prompt: str = ""
    user_query: str = ""
    tier: Tier = Tier.MEDIUM

    # Managed messages (NOT naive append)
    messages: List[Message] = Field(default_factory=list)

    # Structured findings -- the core innovation
    findings: Dict[str, Finding] = Field(default_factory=dict)

    # Budget tracking
    budget: LoopBudget = Field(default_factory=LoopBudget)

    # Failure & recovery
    failed_attempts: List[FailedAttempt] = Field(default_factory=list)

    # Sub-agent tracking
    sub_agents: Dict[str, SubAgentRecord] = Field(default_factory=dict)

    # Audit trail
    cognitive_writes: List[CognitiveWrite] = Field(default_factory=list)

    # Debug snapshots
    iteration_snapshots: List[IterationSnapshot] = Field(default_factory=list)

    # Loop state
    iteration: int = 0
    final_content: Optional[str] = None
    started_at_ns: int = Field(default_factory=time.time_ns)

    # Compaction config -- token-based, not message-count
    compaction_token_ratio: float = 0.8  # compact when est. tokens > 80% of max_context_tokens
    keep_last_n: int = 3  # keep this many recent turns verbatim

    # Nesting info
    depth: int = 0
    parent_turn_id: Optional[str] = None

    # ------------------------------------------------------------------
    # Context building (replaces naive messages list)
    # ------------------------------------------------------------------

    def to_llm_messages(self) -> List[Dict[str, str]]:
        """
        Build the LLM context from scratchpad state.

        Structure:
          1. System prompt (always)
          2. KNOWN FACTS section (structured findings)
          3. BUDGET STATUS section
          4. FAILED ATTEMPTS section (if any)
          5. SUB-AGENT STATUS section (if any)
          6. Original user query
          7. Last N turns verbatim
          8. Older turns -> compacted summary (if present)
        """
        result: List[Dict[str, str]] = []

        # 1. System prompt with injected context sections
        context_sections = [self.system_prompt]

        # 2. Known facts
        facts_summary = self.findings_summary()
        if facts_summary:
            context_sections.append(f"\n## KNOWN FACTS (do NOT re-fetch these)\n{facts_summary}")

        # 3. Budget status + urgency nudge
        remaining_iters = self.budget.remaining_iterations
        budget_lines = [
            "\n## BUDGET STATUS",
            f"- Tool calls remaining: {self.budget.remaining_tools}/{self.budget.max_tools}",
            f"- Iterations remaining: {remaining_iters}/{self.budget.max_iterations}",
            f"- Tools used so far: {self.budget.tools_used}",
        ]
        if remaining_iters <= 5:
            budget_lines.append(
                "\nURGENT: Budget is running low. Stop any information-gathering loops. "
                "Use what you have NOW. Call invoke_capability with best-available params, "
                "then summarize_context, then final_answer. Do NOT call acknowledge or "
                "update_clarifications."
            )
        elif remaining_iters <= 10:
            budget_lines.append(
                "\nNOTE: Over half your budget is used. Prioritize action tools "
                "(invoke_capability, summarize_context) over cognitive tools."
            )
        context_sections.append("\n".join(budget_lines))

        # 4. Failed attempts
        if self.failed_attempts:
            fails = "\n".join(
                f"- {f.tool_name}({f.arguments}): {f.error_code} - {f.error_message} (iter {f.iteration})"
                for f in self.failed_attempts
            )
            context_sections.append(f"\n## PREVIOUSLY FAILED (do NOT retry same args)\n{fails}")

        # 5. Sub-agent status
        active_agents = {
            k: v for k, v in self.sub_agents.items() if v.status != SubAgentStatus.COMPLETE
        }
        completed_agents = {
            k: v for k, v in self.sub_agents.items() if v.status == SubAgentStatus.COMPLETE
        }

        if active_agents or completed_agents:
            agent_lines = []
            for aid, a in completed_agents.items():
                findings_str = ", ".join(f"{f.key}={f.value}" for f in a.findings[:5])
                agent_lines.append(
                    f"- [{a.status.value}] {aid}: {a.task} -> Findings: {findings_str}"
                )
            for aid, a in active_agents.items():
                agent_lines.append(f"- [{a.status.value}] {aid}: {a.task}")
            context_sections.append("\n## SUB-AGENTS\n" + "\n".join(agent_lines))

        result.append({"role": "system", "content": "\n".join(context_sections)})

        # 6-8. Conversation messages
        conversation = [m for m in self.messages if m.role != "system"]

        if len(conversation) <= self.keep_last_n * 2:
            # Few enough messages -- include all verbatim
            for m in conversation:
                result.append({"role": m.role, "content": m.content})
        else:
            # Include compacted summaries first, then last N turns
            compacted = [m for m in conversation if m.is_compacted_summary]
            recent = conversation[-(self.keep_last_n * 2) :]  # last N turn pairs

            for m in compacted:
                result.append({"role": m.role, "content": m.content})
            for m in recent:
                result.append({"role": m.role, "content": m.content})

        return result

    def findings_summary(self) -> str:
        """Format all findings as a concise fact sheet."""
        if not self.findings:
            return ""

        lines = []
        by_type: Dict[str, List[Finding]] = {}
        for f in self.findings.values():
            by_type.setdefault(f.type, []).append(f)

        for ftype, facts in sorted(by_type.items()):
            lines.append(f"### {ftype.upper()}")
            for f in facts:
                conf = f"(confidence: {f.confidence:.0%})" if f.confidence < 1.0 else ""
                lines.append(f"- {f.key}: {f.value} {conf}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Compaction
    # ------------------------------------------------------------------

    def needs_compaction(self) -> bool:
        """Check if estimated context tokens exceed compaction threshold.

        Compacts when the conversation token estimate reaches 80%
        of max_context_tokens.  This replaces the naive message-count
        heuristic (threshold=8) which caused unnecessary compaction
        LLM calls on every iteration.
        """
        conversation = [
            m for m in self.messages if m.role != "system" and not m.is_compacted_summary
        ]
        if not conversation:
            return False
        token_estimate = sum(len(m.content) for m in conversation) // 4
        threshold = int(self.budget.max_context_tokens * self.compaction_token_ratio)
        return token_estimate > threshold

    async def compact_messages(
        self,
        summarizer: Callable[[List[Message]], Coroutine[Any, Any, str]],
    ) -> None:
        """
        Compact older messages using LLM summarization.

        Keeps: system prompt + first user message + last N turns verbatim.
        Summarizes: everything in between into a single digest message.
        Never loses: structured findings (separate from messages).
        """
        conversation = [
            m for m in self.messages if m.role != "system" and not m.is_compacted_summary
        ]

        if len(conversation) <= self.keep_last_n * 2:
            return

        # Split into old and recent
        old_messages = conversation[: -(self.keep_last_n * 2)]
        recent_messages = conversation[-(self.keep_last_n * 2) :]

        if not old_messages:
            return

        # Summarize old messages via LLM
        summary = await summarizer(old_messages)

        # Rebuild message list
        system_msgs = [m for m in self.messages if m.role == "system"]
        first_user = next((m for m in conversation if m.role == "user"), None)

        new_messages = list(system_msgs)
        if first_user and first_user not in recent_messages:
            new_messages.append(first_user)

        new_messages.append(
            Message(
                role="assistant",
                content=f"[COMPACTED SUMMARY of previous {len(old_messages)} messages]\n{summary}",
                is_compacted_summary=True,
            )
        )
        new_messages.extend(recent_messages)

        self.messages = new_messages

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    # Token threshold above which raw tool output is truncated or replaced
    _LARGE_OUTPUT_TOKEN_THRESHOLD: int = 500

    def record_tool_result(
        self,
        call: ToolCall,
        result: ToolResult,
        findings: Optional[List[Finding]] = None,
    ) -> None:
        """Record a tool execution and decrement budget.

        When *findings* are supplied the raw tool output is NOT stored in
        the message history.  Instead a compact digest of the extracted
        findings is kept, which can be orders of magnitude smaller than
        the original payload (e.g. 50 tokens vs 3,500).

        For large outputs where finding extraction has not happened yet
        the result is truncated to a short preview so that the context
        window does not blow up.

        Small outputs (<500 estimated tokens) are stored in full when
        no findings are provided to preserve backward compatibility with
        simple tool calls.
        """
        self.budget.consume_tool()

        # 1. Assistant tool-call marker (always compact)
        self.messages.append(
            Message(
                role="assistant",
                content=f"[Tool call: {call.name}({call.arguments})]",
                tool_call_id=call.call_id,
                tool_name=call.name,
            )
        )

        # 2. Handle failures -- errors are small, always store fully
        if not result.ok:
            self.messages.append(
                Message(
                    role="tool",
                    content=(
                        f"Tool {result.tool_name} FAILED: "
                        f"{result.error_code} - {result.error_message}"
                    ),
                    tool_call_id=call.call_id,
                    tool_name=result.tool_name,
                )
            )
            self.failed_attempts.append(
                FailedAttempt(
                    tool_name=result.tool_name,
                    error_code=result.error_code or "UNKNOWN",
                    error_message=result.error_message or "",
                    iteration=self.iteration,
                    arguments=call.arguments,
                )
            )
            return

        # 3. Successful result -- decide what to store in messages
        result_str = str(result.output) if result.output else ""
        token_estimate = len(result_str) // 4

        if findings:
            # Findings-only mode: store a compact digest
            digest_parts = [f"{f.key}={f.value}" for f in findings[:8]]
            finding_digest = ", ".join(digest_parts)
            self.messages.append(
                Message(
                    role="tool",
                    content=(
                        f"Tool {result.tool_name} completed "
                        f"({token_estimate} raw tokens -> {len(findings)} findings). "
                        f"Extracted: {finding_digest}"
                    ),
                    tool_call_id=call.call_id,
                    tool_name=result.tool_name,
                )
            )
        elif token_estimate > self._LARGE_OUTPUT_TOKEN_THRESHOLD:
            # Large output, no findings -- truncate to preview
            preview = result_str[:200]
            self.messages.append(
                Message(
                    role="tool",
                    content=(
                        f"Tool {result.tool_name} result "
                        f"(large, {token_estimate} tokens, truncated): "
                        f"{preview}... [full data available in findings]"
                    ),
                    tool_call_id=call.call_id,
                    tool_name=result.tool_name,
                )
            )
        else:
            # Small output, no findings -- store in full
            self.messages.append(
                Message(
                    role="tool",
                    content=f"Tool {result.tool_name} result: {result.output}",
                    tool_call_id=call.call_id,
                    tool_name=result.tool_name,
                )
            )

    def add_finding(self, finding: Finding) -> None:
        """Add a structured finding to the scratchpad.

        If the key already exists and comes from a DIFFERENT source tool
        invocation (same tool, different args), namespace it to avoid
        overwriting.  E.g. entity_id -> entity_id_2, entity_id_3 ...
        This prevents data loss when the same tool is called multiple
        times in one iteration (e.g. resolve_entity for Mom, Sarah, Jake).
        """
        finding.source_iteration = self.iteration
        key = finding.key

        if key in self.findings:
            existing = self.findings[key]
            # Same key, same value -> skip duplicate
            if str(existing.value) == str(finding.value):
                return
            # Collision: namespace with incrementing suffix
            n = 2
            while f"{key}_{n}" in self.findings:
                n += 1
            finding.key = f"{key}_{n}"

        self.findings[finding.key] = finding

    def add_findings(self, findings: List[Finding]) -> None:
        """Add multiple findings."""
        for f in findings:
            self.add_finding(f)

    def record_cognitive_write(self, write: CognitiveWrite) -> None:
        """Record a session state mutation for audit."""
        write.iteration = self.iteration
        self.cognitive_writes.append(write)

    def spawn_sub_agent(
        self,
        task: str,
        tool_budget: int = 5,
        depth: int = 1,
    ) -> SubAgentRecord:
        """Create a sub-agent record with a budget slice."""
        agent = SubAgentRecord(
            task=task,
            depth=depth,
            parent_id=self.turn_id,
            budget_consumed=self.budget.slice(tool_budget),
        )
        # Deduct from parent budget
        granted = agent.budget_consumed.max_tools
        self.budget.tools_used += granted
        self.sub_agents[agent.agent_id] = agent
        return agent

    def complete_sub_agent(
        self,
        agent_id: str,
        findings: List[Finding],
        result: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        """Mark a sub-agent as complete and absorb its findings."""
        agent = self.sub_agents.get(agent_id)
        if not agent:
            return

        if error:
            agent.status = SubAgentStatus.FAILED
            agent.error = error
        else:
            agent.status = SubAgentStatus.COMPLETE
            agent.findings = findings
            agent.result = result
            # Absorb findings into parent
            for f in findings:
                self.add_finding(f)

        # Return unused budget
        if agent.budget_consumed:
            self.budget.return_unused(agent.budget_consumed)

    def snapshot_iteration(
        self,
        thought: Optional[str] = None,
        action: Optional[str] = None,
        observation: Optional[str] = None,
        tokens_in: int = 0,
        tokens_out: int = 0,
        duration_ms: int = 0,
        tools_called: Optional[List[str]] = None,
        compacted: bool = False,
    ) -> IterationSnapshot:
        """Capture a debug snapshot of the current iteration."""
        snap = IterationSnapshot(
            iteration=self.iteration,
            thought=thought,
            action=action,
            observation_summary=observation,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            duration_ms=duration_ms,
            context_size_tokens=self._estimate_context_tokens(),
            findings_count=len(self.findings),
            messages_count=len(self.messages),
            compacted=compacted,
            tools_called=tools_called or [],
        )
        self.iteration_snapshots.append(snap)
        self.budget.add_tokens(tokens_in, tokens_out)
        return snap

    # ------------------------------------------------------------------
    # State checks
    # ------------------------------------------------------------------

    def is_complete(self) -> bool:
        """Check if the loop should terminate."""
        return self.final_content is not None or self.budget.exhausted

    def elapsed_ms(self) -> int:
        """Time since scratchpad creation."""
        return (time.time_ns() - self.started_at_ns) // 1_000_000

    def _estimate_context_tokens(self) -> int:
        """Rough token estimate: ~4 chars per token."""
        total_chars = sum(len(m.content) for m in self.messages)
        # Add findings summary
        total_chars += len(self.findings_summary())
        return total_chars // 4


# ---------------------------------------------------------------------------
# Scenario & Checkpoint definitions
# ---------------------------------------------------------------------------


class Checkpoint(BaseModel):
    """An assertion about state at a specific iteration."""

    iteration: int
    check_type: str  # "finding_exists", "finding_value", "budget_remaining", "sub_agent_complete"
    key: str = ""
    expected_value: Any = None
    description: str = ""

    def validate_against(
        self, scratchpad: Optional[Scratchpad] = None, result: Optional[RunResult] = None
    ) -> bool:
        """Check if this checkpoint passes."""
        if self.check_type == "finding_exists" and scratchpad:
            return self.key in scratchpad.findings
        elif self.check_type == "finding_value" and scratchpad:
            f = scratchpad.findings.get(self.key)
            return f is not None and str(f.value) == str(self.expected_value)
        elif self.check_type == "budget_remaining" and scratchpad:
            return scratchpad.budget.remaining_tools >= int(self.expected_value)
        elif self.check_type == "sub_agent_complete" and scratchpad:
            agent = scratchpad.sub_agents.get(self.key)
            return agent is not None and agent.status == SubAgentStatus.COMPLETE
        elif self.check_type == "task_complete" and result:
            return result.success
        elif self.check_type == "context_bounded" and result:
            # Check that context never exceeded the expected value
            max_ctx = max((t.context_tokens_estimate for t in result.turns), default=0)
            return max_ctx <= int(self.expected_value)
        return False


class Scenario(BaseModel):
    """A test scenario definition for the benchmark."""

    id: str
    name: str
    description: str = ""
    system_prompt: str = (
        "You are a helpful research assistant. Use tools to find information and answer the user's question accurately."
    )
    user_query: str = ""
    tier: Tier = Tier.MEDIUM
    max_iterations: int = 10
    max_tools: int = 10
    expected_tool_sequence: List[str] = Field(default_factory=list)  # hints for validation
    checkpoints: List[Checkpoint] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)  # categorization
    registry: str = "canned"  # "canned" or "concierge" -- selects which ToolRegistry to use
    force_tool_call: bool = (
        False  # force LLM to return function calls (not text) via tool_config mode=ANY
    )
    min_tool_iterations: int = (
        0  # withhold final_answer from tool declarations for first N iterations
    )
