"""
Cognitive Envelope for Concierge PoC

This module implements the cognitive envelope design from envelope_design.md,
building on the base envelope.schema.json with Concierge-specific extensions.

Research Basis:
- Actor Model (Hewitt 1973): Envelope = message between actors
- Conversational Grounding (Clark 1991): QUD + scoreboard track common ground
- Mixed-Initiative (Allen 1999): Intent + spawn fields enable proactive behavior
- Progressive Disclosure (Norman 1988): Progress policy controls information flow

ADR References:
- ADR-0002: Actor Model for Agent Isolation
"""

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class CognitiveEnvelope:
    """
    Cognitive envelope for Concierge PoC reactive-proactive loop.

    Contains base fields from envelope.schema.json plus Concierge-specific
    extensions for intent classification, conversation state, specialist
    spawning, and progress tracking.

    **Base Fields (Required):**
    - schema_version: Envelope schema version
    - envelope_id: Unique ID (UUIDv7, auto-generated)
    - ts: ISO8601 timestamp (auto-generated)
    - sender: Agent identifier
    - receiver: Target agent/user
    - kind: Semantic message type
    - conversation_id: Conversation identifier
    - cognitive_trace_id: End-to-end trace ID

    **Concierge Extensions:**
    - actor: Identity and authorization context
    - policy: Capability-based access control
    - intent: Intent classification result
    - conversation: QUD + scoreboard + affect
    - spawn: Specialist spawn request
    - progress_policy: Progress update controls
    - telemetry: Performance tracking
    - observability: Tracing and validation
    - body: Flexible payload per kind
    """

    # ===== Required Base Fields =====
    schema_version: str = "1.0.0"
    envelope_id: Optional[str] = None
    ts: Optional[str] = None
    sender: Optional[str] = None
    receiver: Optional[str] = None
    kind: Optional[str] = None
    conversation_id: Optional[str] = None
    cognitive_trace_id: Optional[str] = None

    # ===== Optional Base Fields =====
    priority: str = "interactive"
    delivery_semantics: str = "at_least_once"
    caused_by: Optional[List[str]] = None
    task_id: Optional[str] = None
    parent_task_id: Optional[str] = None
    expects_reply: bool = False

    # ===== Concierge-Specific Extensions =====
    actor: Optional[Dict[str, Any]] = None
    policy: Optional[Dict[str, Any]] = None
    intent: Optional[Dict[str, Any]] = None
    conversation: Optional[Dict[str, Any]] = None
    spawn: Optional[Dict[str, Any]] = None
    progress_policy: Optional[Dict[str, Any]] = None
    telemetry: Optional[Dict[str, Any]] = None
    observability: Optional[Dict[str, Any]] = None
    body: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        """Auto-generate envelope_id and ts if not provided."""
        if self.envelope_id is None:
            self.envelope_id = self._generate_ulid()
        if self.ts is None:
            self.ts = datetime.utcnow().isoformat() + "Z"

    def _generate_ulid(self) -> str:
        """
        Generate UUIDv7 (time-ordered, K-sortable).

        UUIDv7 provides:
        - Time-ordered: Can be sorted by creation time
        - K-sortability: Efficient database indexing
        - Uniqueness: No collisions

        Returns:
            str: UUIDv7 string (e.g., "01JA1B2C3D4E5F6G7H8J9K")
        """
        # Python 3.12+ has uuid.uuid7()
        try:
            return str(uuid.uuid7())
        except AttributeError:
            # Fallback to uuid4 for Python <3.12
            return str(uuid.uuid4())

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert envelope to dictionary, removing None values.

        This creates a clean JSON-serializable dict with only
        fields that have been set, matching the envelope_design.md
        examples.

        Returns:
            dict: Envelope as dictionary (no None values)
        """
        return {k: v for k, v in asdict(self).items() if v is not None}

    def to_json(self) -> str:
        """
        Serialize envelope to JSON string.

        Returns:
            str: JSON-formatted envelope
        """
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CognitiveEnvelope":
        """
        Deserialize envelope from dictionary.

        Args:
            data: Dictionary with envelope fields

        Returns:
            CognitiveEnvelope: Reconstructed envelope
        """
        return cls(**data)

    def validate(self) -> Tuple[bool, List[str]]:
        """
        Validate envelope against schema requirements.

        Checks:
        - Required fields present
        - Kind-specific field validation
        - Budget enforcement (latency, cost)
        - Policy constraints (capabilities, bands)

        Returns:
            tuple: (is_valid, list_of_errors)
        """
        errors = []

        # Required fields
        required = [
            "schema_version",
            "envelope_id",
            "ts",
            "sender",
            "kind",
            "conversation_id",
            "cognitive_trace_id",
        ]
        for field_name in required:
            if getattr(self, field_name) is None:
                errors.append(f"Missing required field: {field_name}")

        # Kind-specific validation
        if self.kind:
            kind_errors = self._validate_kind_specific()
            errors.extend(kind_errors)

        # Budget enforcement
        if self.telemetry:
            budget_errors = self._validate_budget()
            errors.extend(budget_errors)

        # Policy validation
        if self.policy:
            policy_errors = self._validate_policy()
            errors.extend(policy_errors)

        return len(errors) == 0, errors

    def _validate_kind_specific(self) -> List[str]:
        """Validate kind-specific required fields."""
        errors = []

        if self.kind == "reactive_response":
            if not self.intent:
                errors.append("reactive_response requires intent field")
            if not self.conversation:
                errors.append("reactive_response requires conversation field")

        elif self.kind == "proactive_prompt":
            if not self.body or "strategy" not in self.body:
                errors.append("proactive_prompt requires body.strategy")
            if not self.body or "information_target" not in self.body:
                errors.append("proactive_prompt requires body.information_target")

        elif self.kind == "spawn_specialist":
            if not self.spawn or not self.spawn.get("requested"):
                errors.append("spawn_specialist requires spawn.requested: true")
            if not self.spawn or not self.spawn.get("specialist"):
                errors.append("spawn_specialist requires spawn.specialist")

        elif self.kind == "progress_event":
            if not self.body or "milestone" not in self.body:
                errors.append("progress_event requires body.milestone")
            if not self.body or "percent" not in self.body:
                errors.append("progress_event requires body.percent")

        elif self.kind == "specialist_result":
            if not self.body or "insights" not in self.body:
                errors.append("specialist_result requires body.insights")
            if not self.body or "confidence" not in self.body:
                errors.append("specialist_result requires body.confidence")

        elif self.kind == "synthesis_response":
            if not self.body or "text" not in self.body:
                errors.append("synthesis_response requires body.text")

        elif self.kind == "user_utterance":
            if not self.body or "text" not in self.body:
                errors.append("user_utterance requires body.text")

        return errors

    def _validate_budget(self) -> List[str]:
        """Validate performance budgets."""
        errors = []

        if (
            self.telemetry
            and "latency_budget_ms" in self.telemetry
            and "total_latency_ms" in self.telemetry
        ):
            budget = self.telemetry["latency_budget_ms"]
            actual = self.telemetry["total_latency_ms"]
            if actual > budget:
                errors.append(f"Budget exceeded: {actual}ms > {budget}ms")

        if (
            self.policy
            and self.telemetry
            and "budget_ceiling_usd" in self.policy
            and "total_cost_usd" in self.telemetry
        ):
            ceiling = self.policy["budget_ceiling_usd"]
            actual = self.telemetry["total_cost_usd"]
            if actual > ceiling:
                errors.append(f"Cost budget exceeded: ${actual:.4f} > ${ceiling:.4f}")

        return errors

    def _validate_policy(self) -> List[str]:
        """Validate policy constraints."""
        errors = []

        # Validate band is valid
        if self.policy and "band" in self.policy:
            band = self.policy["band"]
            if band not in ["GREEN", "AMBER", "RED"]:
                errors.append(f"Invalid policy band: {band}")

        # Validate capabilities format
        if self.policy and "caps" in self.policy:
            caps = self.policy["caps"]
            if not isinstance(caps, list):
                errors.append("policy.caps must be a list")

        return errors


class EnvelopeFactory:
    """
    Factory for creating typed cognitive envelopes.

    Provides static methods to create envelopes for each kind of message
    in the Concierge PoC reactive-proactive loop, ensuring correct field
    population and consistency.
    """

    @staticmethod
    def create_user_utterance(
        user_id: str,
        conversation_id: str,
        text: str,
        trace_id: str,
        session_id: Optional[str] = None,
    ) -> CognitiveEnvelope:
        """
        Create user message envelope.

        Args:
            user_id: FamilyOS user ID
            conversation_id: Conversation identifier
            text: User's message text
            trace_id: Cognitive trace ID
            session_id: Browser/app session ID

        Returns:
            CognitiveEnvelope: User utterance envelope
        """
        return CognitiveEnvelope(
            sender=f"user:{user_id}",
            receiver="concierge.agent",
            kind="user_utterance",
            conversation_id=conversation_id,
            cognitive_trace_id=trace_id,
            priority="interactive",
            actor={
                "agent": None,
                "user_id": user_id,
                "space_id": f"personal:{user_id}",
                "session_id": session_id,
            },
            policy={
                "band": "GREEN",
                "caps": ["read.k0"],
                "budget_ceiling_usd": 0.10,
                "human_approval_required": False,
            },
            body={"text": text, "input_modality": "text", "channel": "web"},
            telemetry={"latency_budget_ms": 1200, "perf_profile": "PATH1"},
            observability={
                "trace_flags": ["sse.stream", "proactive.enabled"],
                "research_pattern": "reactive_proactive_loop",
            },
        )

    @staticmethod
    def create_reactive_response(
        user_id: str,
        conversation_id: str,
        trace_id: str,
        caused_by: str,
        intent: Dict[str, Any],
        conversation_state: Dict[str, Any],
        affect: Dict[str, Any],
        empathy_text: str,
        action_declaration: str,
        llm_calls: List[Dict[str, Any]],
    ) -> CognitiveEnvelope:
        """
        Create reactive response envelope.

        Args:
            user_id: FamilyOS user ID
            conversation_id: Conversation identifier
            trace_id: Cognitive trace ID
            caused_by: Upstream envelope ID
            intent: Intent classification result
            conversation_state: QUD + scoreboard + affect
            affect: Detected emotion
            empathy_text: Empathy response
            action_declaration: Action being taken
            llm_calls: List of LLM call metrics

        Returns:
            CognitiveEnvelope: Reactive response envelope
        """
        total_latency = sum(call.get("latency_ms", 0) for call in llm_calls)

        return CognitiveEnvelope(
            sender="concierge.agent",
            receiver=f"user:{user_id}",
            kind="reactive_response",
            conversation_id=conversation_id,
            cognitive_trace_id=trace_id,
            caused_by=[caused_by],
            actor={"agent": "concierge", "user_id": user_id, "space_id": f"personal:{user_id}"},
            intent=intent,
            conversation=conversation_state,
            body={
                "text": f"{empathy_text}. {action_declaration}.",
                "empathy": empathy_text,
                "action_declaration": action_declaration,
                "generation_method": "rule_based",
            },
            telemetry={
                "latency_budget_ms": 1200,
                "llm_calls": llm_calls,
                "total_latency_ms": total_latency,
            },
            observability={
                "stamps": [
                    {
                        "stage": "concierge.intent_classification",
                        "rtt_ms": llm_calls[0].get("latency_ms", 0) if llm_calls else 0,
                        "intent_conf": intent.get("confidence", 0),
                    },
                    {"stage": "concierge.reactive_response", "rtt_ms": total_latency},
                ]
            },
        )

    @staticmethod
    def create_proactive_prompt(
        user_id: str,
        conversation_id: str,
        trace_id: str,
        caused_by: str,
        prompt_text: str,
        strategy: str,
        information_target: str,
        information_gaps: List[str],
        conversation_state: Dict[str, Any],
        llm_calls: List[Dict[str, Any]],
    ) -> CognitiveEnvelope:
        """
        Create proactive prompt envelope.

        Args:
            user_id: FamilyOS user ID
            conversation_id: Conversation identifier
            trace_id: Cognitive trace ID
            caused_by: Upstream envelope ID
            prompt_text: Generated proactive prompt
            strategy: fill_gap, future_action, or clarify
            information_target: What info being requested
            information_gaps: List of identified gaps
            conversation_state: QUD + scoreboard
            llm_calls: List of LLM call metrics

        Returns:
            CognitiveEnvelope: Proactive prompt envelope
        """
        total_latency = sum(call.get("latency_ms", 0) for call in llm_calls)

        return CognitiveEnvelope(
            sender="concierge.agent",
            receiver=f"user:{user_id}",
            kind="proactive_prompt",
            conversation_id=conversation_id,
            cognitive_trace_id=trace_id,
            caused_by=[caused_by],
            actor={"agent": "concierge", "user_id": user_id},
            conversation=conversation_state,
            body={
                "text": prompt_text,
                "strategy": strategy,
                "information_target": information_target,
                "information_gaps": information_gaps,
                "generation_method": "llm",
            },
            telemetry={"llm_calls": llm_calls, "total_latency_ms": total_latency},
            observability={
                "stamps": [
                    {
                        "stage": "concierge.gap_identification",
                        "rtt_ms": llm_calls[0].get("latency_ms", 0) if llm_calls else 0,
                    },
                    {
                        "stage": "concierge.proactive_prompt",
                        "rtt_ms": llm_calls[1].get("latency_ms", 0) if len(llm_calls) > 1 else 0,
                        "note": f"{strategy} strategy",
                    },
                ]
            },
        )

    @staticmethod
    def create_spawn_specialist(
        user_id: str,
        conversation_id: str,
        trace_id: str,
        caused_by: str,
        specialist_type: str,
        task_id: str,
        query: str,
        est_duration_ms: int,
        context: Dict[str, Any],
        progress_milestones: List[Dict[str, Any]],
    ) -> CognitiveEnvelope:
        """
        Create specialist spawn request envelope.

        Args:
            user_id: FamilyOS user ID
            conversation_id: Conversation identifier
            trace_id: Cognitive trace ID
            caused_by: Upstream envelope ID
            specialist_type: Type of specialist (nutritionist, etc.)
            task_id: Unique task identifier
            query: Query for specialist
            est_duration_ms: Estimated task duration
            context: Additional context (user_hypothesis, time_range, etc.)
            progress_milestones: List of milestone definitions

        Returns:
            CognitiveEnvelope: Spawn specialist envelope
        """
        return CognitiveEnvelope(
            sender="concierge.agent",
            receiver="actor_fabric.spawn_manager",
            kind="spawn_specialist",
            conversation_id=conversation_id,
            cognitive_trace_id=trace_id,
            caused_by=[caused_by],
            priority="background",
            task_id=task_id,
            actor={"agent": "concierge", "user_id": user_id, "space_id": f"personal:{user_id}"},
            policy={"band": "GREEN", "caps": ["read.k0", f"spawn.{specialist_type}"]},
            spawn={
                "requested": True,
                "specialist": specialist_type,
                "task_id": task_id,
                "parent_trace_id": trace_id,
                "est_duration_ms": est_duration_ms,
                "query": query,
                "context": context,
            },
            progress_policy={
                "max_updates_per_sec": 5,
                "merge_window_ms": 120,
                "milestones": progress_milestones,
                "enable_streaming": True,
                "debounce_ms": 50,
            },
            telemetry={"latency_budget_ms": 1000, "perf_profile": "PATH1"},
        )

    @staticmethod
    def create_progress_event(
        specialist_type: str,
        conversation_id: str,
        trace_id: str,
        task_id: str,
        milestone: int,
        percent: int,
        message: str,
    ) -> CognitiveEnvelope:
        """
        Create progress update envelope.

        Args:
            specialist_type: Type of specialist
            conversation_id: Conversation identifier
            trace_id: Cognitive trace ID
            task_id: Task identifier
            milestone: Milestone number (1-5)
            percent: Completion percentage (0-100)
            message: Progress message

        Returns:
            CognitiveEnvelope: Progress event envelope
        """
        return CognitiveEnvelope(
            sender=f"{specialist_type}.agent",
            receiver="concierge.agent",
            kind="progress_event",
            conversation_id=conversation_id,
            cognitive_trace_id=trace_id,
            task_id=task_id,
            body={
                "milestone": milestone,
                "percent": percent,
                "message": message,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            },
        )

    @staticmethod
    def create_specialist_result(
        specialist_type: str,
        conversation_id: str,
        trace_id: str,
        task_id: str,
        caused_by: str,
        query: str,
        insights: List[Dict[str, Any]],
        evidence: List[str],
        confidence: float,
        duration_ms: int,
        contradicts_user_hypothesis: bool = False,
        user_hypothesis: Optional[str] = None,
        actual_finding: Optional[str] = None,
    ) -> CognitiveEnvelope:
        """
        Create specialist result envelope.

        Args:
            specialist_type: Type of specialist
            conversation_id: Conversation identifier
            trace_id: Cognitive trace ID
            task_id: Task identifier
            caused_by: Spawn request envelope ID
            query: Original query
            insights: List of insight dicts
            evidence: List of evidence strings
            confidence: Overall confidence score
            duration_ms: Specialist execution time
            contradicts_user_hypothesis: Whether result contradicts user
            user_hypothesis: User's original assumption
            actual_finding: Actual finding from analysis

        Returns:
            CognitiveEnvelope: Specialist result envelope
        """
        body: Dict[str, Any] = {
            "specialist_type": specialist_type,
            "query": query,
            "insights": insights,
            "evidence": evidence,
            "confidence": confidence,
        }

        if contradicts_user_hypothesis:
            body["contradicts_user_hypothesis"] = True  # type: ignore
            body["user_hypothesis"] = user_hypothesis  # type: ignore
            body["actual_finding"] = actual_finding  # type: ignore

        return CognitiveEnvelope(
            sender=f"{specialist_type}.agent",
            receiver="concierge.agent",
            kind="specialist_result",
            conversation_id=conversation_id,
            cognitive_trace_id=trace_id,
            task_id=task_id,
            caused_by=[caused_by],
            body=body,
            telemetry={"specialist_duration_ms": duration_ms},
        )

    @staticmethod
    def create_synthesis_response(
        user_id: str,
        conversation_id: str,
        trace_id: str,
        caused_by: str,
        synthesis_text: str,
        specialist_type: str,
        conversation_state: Dict[str, Any],
        contradiction_detected: bool,
        user_assumption: Optional[str],
        actual_finding: Optional[str],
        llm_calls: List[Dict[str, Any]],
        specialist_duration_ms: int,
    ) -> CognitiveEnvelope:
        """
        Create synthesis response envelope.

        Args:
            user_id: FamilyOS user ID
            conversation_id: Conversation identifier
            trace_id: Cognitive trace ID
            caused_by: Specialist result envelope ID
            synthesis_text: Generated synthesis
            specialist_type: Type of specialist
            conversation_state: QUD + scoreboard
            contradiction_detected: Whether contradiction found
            user_assumption: User's original assumption
            actual_finding: Actual finding from specialist
            llm_calls: List of all LLM call metrics
            specialist_duration_ms: Specialist execution time

        Returns:
            CognitiveEnvelope: Synthesis response envelope
        """
        total_latency = (
            sum(call.get("latency_ms", 0) for call in llm_calls) + specialist_duration_ms
        )
        total_cost = sum(call.get("cost_usd", 0) for call in llm_calls)

        body = {
            "text": synthesis_text,
            "specialist_type": specialist_type,
            "generation_method": "llm",
        }

        if contradiction_detected:
            body["contradiction_detected"] = True
            body["user_assumption"] = user_assumption
            body["actual_finding"] = actual_finding

        return CognitiveEnvelope(
            sender="concierge.agent",
            receiver=f"user:{user_id}",
            kind="synthesis_response",
            conversation_id=conversation_id,
            cognitive_trace_id=trace_id,
            caused_by=[caused_by],
            conversation=conversation_state,
            body=body,
            telemetry={
                "latency_budget_ms": 1200,
                "llm_calls": llm_calls,
                "specialist_duration_ms": specialist_duration_ms,
                "total_latency_ms": total_latency,
                "budget_exceeded": total_latency > 1200,
                "total_cost_usd": total_cost,
            },
            observability={
                "stamps": [
                    {
                        "stage": "concierge.synthesis",
                        "rtt_ms": llm_calls[-1].get("latency_ms", 0) if llm_calls else 0,
                    }
                ],
                "research_pattern": "reactive_proactive_loop",
            },
        )


class EnvelopeValidator:
    """
    Validator for cognitive envelopes.

    Provides static methods to validate envelope dictionaries against
    schema requirements, kind-specific rules, budget constraints, and
    policy requirements.
    """

    @staticmethod
    def validate_envelope(envelope: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate envelope against schema requirements.

        Checks:
        - Required fields present
        - Kind-specific field validation
        - Budget enforcement (latency, cost)
        - Policy constraints (capabilities, bands)

        Args:
            envelope: Envelope dictionary to validate

        Returns:
            tuple: (is_valid, list_of_errors)
        """
        errors = []

        # Required fields
        required = [
            "schema_version",
            "envelope_id",
            "ts",
            "sender",
            "kind",
            "conversation_id",
            "cognitive_trace_id",
        ]
        for field_name in required:
            if field_name not in envelope:
                errors.append(f"Missing required field: {field_name}")

        # Kind-specific validation
        kind = envelope.get("kind")
        if kind:
            kind_errors = EnvelopeValidator._validate_kind_specific(envelope, kind)
            errors.extend(kind_errors)

        # Budget enforcement
        if "telemetry" in envelope:
            budget_errors = EnvelopeValidator._validate_budget(envelope)
            errors.extend(budget_errors)

        # Policy validation
        if "policy" in envelope:
            policy_errors = EnvelopeValidator._validate_policy(envelope)
            errors.extend(policy_errors)

        return len(errors) == 0, errors

    @staticmethod
    def _validate_kind_specific(envelope: Dict[str, Any], kind: str) -> List[str]:
        """Validate kind-specific required fields."""
        errors = []
        body = envelope.get("body", {})

        if kind == "reactive_response":
            if "intent" not in envelope:
                errors.append("reactive_response requires intent field")
            if "conversation" not in envelope:
                errors.append("reactive_response requires conversation field")

        elif kind == "proactive_prompt":
            if "strategy" not in body:
                errors.append("proactive_prompt requires body.strategy")
            if body.get("strategy") not in ["fill_gap", "future_action", "clarify"]:
                errors.append(f"Invalid proactive strategy: {body.get('strategy')}")

        elif kind == "spawn_specialist":
            spawn = envelope.get("spawn", {})
            if not spawn.get("requested"):
                errors.append("spawn_specialist requires spawn.requested: true")
            if not spawn.get("specialist"):
                errors.append("spawn_specialist requires spawn.specialist")

        elif kind == "progress_event":
            if "milestone" not in body:
                errors.append("progress_event requires body.milestone")
            if "percent" not in body:
                errors.append("progress_event requires body.percent")
            percent = body.get("percent", 0)
            if not 0 <= percent <= 100:
                errors.append(f"Invalid percent: {percent} (must be 0-100)")

        elif kind == "specialist_result":
            if "insights" not in body:
                errors.append("specialist_result requires body.insights")
            if "confidence" not in body:
                errors.append("specialist_result requires body.confidence")

        elif kind == "synthesis_response":
            if "text" not in body:
                errors.append("synthesis_response requires body.text")

        elif kind == "user_utterance":
            if "text" not in body:
                errors.append("user_utterance requires body.text")

        return errors

    @staticmethod
    def _validate_budget(envelope: Dict[str, Any]) -> List[str]:
        """Validate performance budgets."""
        errors = []
        telemetry = envelope.get("telemetry", {})
        policy = envelope.get("policy", {})

        # Latency budget
        if "latency_budget_ms" in telemetry and "total_latency_ms" in telemetry:
            budget = telemetry["latency_budget_ms"]
            actual = telemetry["total_latency_ms"]
            if actual > budget:
                errors.append(f"Budget exceeded: {actual}ms > {budget}ms")

        # Cost budget
        if "budget_ceiling_usd" in policy and "total_cost_usd" in telemetry:
            ceiling = policy["budget_ceiling_usd"]
            actual = telemetry["total_cost_usd"]
            if actual > ceiling:
                errors.append(f"Cost budget exceeded: ${actual:.4f} > ${ceiling:.4f}")

        return errors

    @staticmethod
    def _validate_policy(envelope: Dict[str, Any]) -> List[str]:
        """Validate policy constraints."""
        errors = []
        policy = envelope.get("policy", {})

        # Validate band
        if "band" in policy:
            band = policy["band"]
            if band not in ["GREEN", "AMBER", "RED"]:
                errors.append(f"Invalid policy band: {band}")

        # Validate capabilities format
        if "caps" in policy:
            caps = policy["caps"]
            if not isinstance(caps, list):
                errors.append("policy.caps must be a list")
            else:
                # Validate capability format (should be dot-separated)
                for cap in caps:
                    if not isinstance(cap, str) or "." not in cap:
                        errors.append(f"Invalid capability format: {cap}")

        # Validate human approval consistency
        if policy.get("band") == "RED" and not policy.get("human_approval_required"):
            errors.append("RED band requires human_approval_required: true")

        return errors
