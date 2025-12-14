"""
Unit tests for CognitiveEnvelope, EnvelopeFactory, and EnvelopeValidator.

Tests cover:
- Envelope creation and serialization
- Factory methods for all envelope kinds
- Validation rules (required fields, kind-specific, budgets, policy)
- Round-trip serialization (to_dict/from_dict)
"""

from backend.models.envelope import CognitiveEnvelope, EnvelopeFactory, EnvelopeValidator


class TestCognitiveEnvelope:
    """Test CognitiveEnvelope dataclass."""

    def test_envelope_creation_minimal(self):
        """Test creating envelope with minimal required fields."""
        envelope = CognitiveEnvelope(
            sender="test.agent",
            receiver="user:123",
            kind="user_utterance",
            conversation_id="conv_123",
            cognitive_trace_id="trace_123",
        )

        assert envelope.sender == "test.agent"
        assert envelope.receiver == "user:123"
        assert envelope.kind == "user_utterance"
        assert envelope.schema_version == "1.0.0"
        assert envelope.envelope_id is not None  # Auto-generated
        assert envelope.ts is not None  # Auto-generated

    def test_envelope_auto_generation(self):
        """Test auto-generation of envelope_id and ts."""
        envelope1 = CognitiveEnvelope(
            sender="test", kind="test", conversation_id="conv", cognitive_trace_id="trace"
        )
        envelope2 = CognitiveEnvelope(
            sender="test", kind="test", conversation_id="conv", cognitive_trace_id="trace"
        )

        # Should have unique IDs
        assert envelope1.envelope_id != envelope2.envelope_id

        # Should have timestamps
        assert envelope1.ts.endswith("Z")
        assert envelope2.ts.endswith("Z")

    def test_envelope_to_dict(self):
        """Test envelope serialization to dictionary."""
        envelope = CognitiveEnvelope(
            sender="test.agent",
            receiver="user:123",
            kind="user_utterance",
            conversation_id="conv_123",
            cognitive_trace_id="trace_123",
            body={"text": "hello"},
        )

        data = envelope.to_dict()

        assert isinstance(data, dict)
        assert data["sender"] == "test.agent"
        assert data["receiver"] == "user:123"
        assert data["kind"] == "user_utterance"
        assert data["body"] == {"text": "hello"}
        assert "envelope_id" in data
        assert "ts" in data

        # None values should be excluded
        assert "parent_task_id" not in data

    def test_envelope_to_json(self):
        """Test envelope serialization to JSON string."""
        envelope = CognitiveEnvelope(
            sender="test.agent", kind="test", conversation_id="conv", cognitive_trace_id="trace"
        )

        json_str = envelope.to_json()

        assert isinstance(json_str, str)
        assert "test.agent" in json_str
        assert "envelope_id" in json_str

    def test_envelope_from_dict(self):
        """Test envelope deserialization from dictionary."""
        data = {
            "schema_version": "1.0.0",
            "envelope_id": "test_id_123",
            "ts": "2025-11-08T10:00:00Z",
            "sender": "test.agent",
            "receiver": "user:123",
            "kind": "user_utterance",
            "conversation_id": "conv_123",
            "cognitive_trace_id": "trace_123",
        }

        envelope = CognitiveEnvelope.from_dict(data)

        assert envelope.envelope_id == "test_id_123"
        assert envelope.sender == "test.agent"
        assert envelope.kind == "user_utterance"

    def test_envelope_round_trip(self):
        """Test envelope survives to_dict -> from_dict round trip."""
        original = CognitiveEnvelope(
            sender="test.agent",
            receiver="user:123",
            kind="reactive_response",
            conversation_id="conv_123",
            cognitive_trace_id="trace_123",
            intent={"type": "QUERY", "domain": "health"},
            conversation={"qud": "What is GERD?"},
            body={"text": "Let me check"},
        )

        data = original.to_dict()
        restored = CognitiveEnvelope.from_dict(data)

        assert restored.sender == original.sender
        assert restored.kind == original.kind
        assert restored.intent == original.intent
        assert restored.conversation == original.conversation
        assert restored.body == original.body

    def test_envelope_validation_success(self):
        """Test successful envelope validation."""
        envelope = CognitiveEnvelope(
            sender="test.agent",
            receiver="user:123",
            kind="user_utterance",
            conversation_id="conv_123",
            cognitive_trace_id="trace_123",
            body={"text": "hello"},
        )

        is_valid, errors = envelope.validate()

        assert is_valid is True
        assert len(errors) == 0

    def test_envelope_validation_missing_required(self):
        """Test validation fails when required fields missing."""
        envelope = CognitiveEnvelope(
            sender=None,  # Missing required field
            kind="test",
            conversation_id="conv",
            cognitive_trace_id="trace",
        )

        is_valid, errors = envelope.validate()

        assert is_valid is False
        assert any("Missing required field: sender" in err for err in errors)

    def test_envelope_validation_kind_specific_reactive_response(self):
        """Test kind-specific validation for reactive_response."""
        envelope = CognitiveEnvelope(
            sender="concierge.agent",
            kind="reactive_response",
            conversation_id="conv",
            cognitive_trace_id="trace",
            # Missing intent and conversation fields
        )

        is_valid, errors = envelope.validate()

        assert is_valid is False
        assert any("intent" in err for err in errors)
        assert any("conversation" in err for err in errors)

    def test_envelope_validation_kind_specific_proactive_prompt(self):
        """Test kind-specific validation for proactive_prompt."""
        envelope = CognitiveEnvelope(
            sender="concierge.agent",
            kind="proactive_prompt",
            conversation_id="conv",
            cognitive_trace_id="trace",
            body={"text": "prompt"},  # Missing strategy
        )

        is_valid, errors = envelope.validate()

        assert is_valid is False
        assert any("strategy" in err for err in errors)

    def test_envelope_validation_budget_exceeded(self):
        """Test budget enforcement validation."""
        envelope = CognitiveEnvelope(
            sender="test",
            kind="synthesis_response",
            conversation_id="conv",
            cognitive_trace_id="trace",
            telemetry={"latency_budget_ms": 1000, "total_latency_ms": 1500},  # Exceeds budget
            body={"text": "result"},
        )

        is_valid, errors = envelope.validate()

        assert is_valid is False
        assert any("Budget exceeded" in err for err in errors)

    def test_envelope_validation_invalid_policy_band(self):
        """Test policy validation for invalid band."""
        envelope = CognitiveEnvelope(
            sender="test",
            kind="test",
            conversation_id="conv",
            cognitive_trace_id="trace",
            policy={"band": "INVALID"},  # Invalid band
        )

        is_valid, errors = envelope.validate()

        assert is_valid is False
        assert any("Invalid policy band" in err for err in errors)


class TestEnvelopeFactory:
    """Test EnvelopeFactory static methods."""

    def test_create_user_utterance(self):
        """Test creating user utterance envelope."""
        envelope = EnvelopeFactory.create_user_utterance(
            user_id="user_123",
            conversation_id="conv_abc",
            text="milk is making me sick",
            trace_id="trace_xyz",
            session_id="sess_123",
        )

        assert envelope.sender == "user:user_123"
        assert envelope.receiver == "concierge.agent"
        assert envelope.kind == "user_utterance"
        assert envelope.body["text"] == "milk is making me sick"
        assert envelope.actor["user_id"] == "user_123"
        assert envelope.policy["band"] == "GREEN"

    def test_create_reactive_response(self):
        """Test creating reactive response envelope."""
        intent = {
            "type": "QUERY",
            "domain": "health",
            "complexity": "simple",
            "specialist_type": "nutritionist",
            "confidence": 0.92,
        }
        conversation_state = {"qud": "What is causing GERD?", "scoreboard": {"referents": {}}}
        affect = {"label": "concerned", "confidence": 0.8}
        llm_calls = [{"operation": "intent_classification", "latency_ms": 28, "cost_usd": 0.0001}]

        envelope = EnvelopeFactory.create_reactive_response(
            user_id="user_123",
            conversation_id="conv_abc",
            trace_id="trace_xyz",
            caused_by="env_upstream",
            intent=intent,
            conversation_state=conversation_state,
            affect=affect,
            empathy_text="That's sad to hear",
            action_declaration="Looping in nutritionist",
            llm_calls=llm_calls,
        )

        assert envelope.kind == "reactive_response"
        assert envelope.intent == intent
        assert envelope.conversation == conversation_state
        assert "That's sad to hear" in envelope.body["text"]
        assert envelope.telemetry["total_latency_ms"] == 28

    def test_create_proactive_prompt(self):
        """Test creating proactive prompt envelope."""
        conversation_state = {"qud": "What is GERD?", "scoreboard": {}}
        llm_calls = [
            {"operation": "gap_identification", "latency_ms": 45, "cost_usd": 0.0002},
            {"operation": "proactive_prompt", "latency_ms": 105, "cost_usd": 0.0005},
        ]

        envelope = EnvelopeFactory.create_proactive_prompt(
            user_id="user_123",
            conversation_id="conv_abc",
            trace_id="trace_xyz",
            caused_by="env_upstream",
            prompt_text="Until nutritionist gathers data, why can't you tell me how uneasy it was?",
            strategy="fill_gap",
            information_target="pain_severity",
            information_gaps=["pain_severity", "pain_location"],
            conversation_state=conversation_state,
            llm_calls=llm_calls,
        )

        assert envelope.kind == "proactive_prompt"
        assert envelope.body["strategy"] == "fill_gap"
        assert envelope.body["information_target"] == "pain_severity"
        assert envelope.telemetry["total_latency_ms"] == 150

    def test_create_spawn_specialist(self):
        """Test creating spawn specialist envelope."""
        milestones = [
            {"milestone": 1, "percent": 20, "message": "Checking diet history"},
            {"milestone": 2, "percent": 40, "message": "Analyzing patterns"},
        ]

        envelope = EnvelopeFactory.create_spawn_specialist(
            user_id="user_123",
            conversation_id="conv_abc",
            trace_id="trace_xyz",
            caused_by="env_upstream",
            specialist_type="nutritionist",
            task_id="task_123",
            query="What foods trigger GERD?",
            est_duration_ms=800,
            context={"user_hypothesis": "milk", "time_range": "last_30_days"},
            progress_milestones=milestones,
        )

        assert envelope.kind == "spawn_specialist"
        assert envelope.receiver == "actor_fabric.spawn_manager"
        assert envelope.spawn["requested"] is True
        assert envelope.spawn["specialist"] == "nutritionist"
        assert envelope.progress_policy["milestones"] == milestones

    def test_create_progress_event(self):
        """Test creating progress event envelope."""
        envelope = EnvelopeFactory.create_progress_event(
            specialist_type="nutritionist",
            conversation_id="conv_abc",
            trace_id="trace_xyz",
            task_id="task_123",
            milestone=2,
            percent=40,
            message="Analyzing patterns...",
        )

        assert envelope.kind == "progress_event"
        assert envelope.sender == "nutritionist.agent"
        assert envelope.body["milestone"] == 2
        assert envelope.body["percent"] == 40

    def test_create_specialist_result(self):
        """Test creating specialist result envelope."""
        insights = [
            {
                "summary": "Strong trigger: coffee",
                "evidence": ["3 out of 5 times"],
                "severity": "strong",
                "confidence": 0.85,
            }
        ]
        evidence = ["2025-11-01: Coffee -> GERD"]

        envelope = EnvelopeFactory.create_specialist_result(
            specialist_type="nutritionist",
            conversation_id="conv_abc",
            trace_id="trace_xyz",
            task_id="task_123",
            caused_by="env_spawn",
            query="What triggers GERD?",
            insights=insights,
            evidence=evidence,
            confidence=0.85,
            duration_ms=850,
            contradicts_user_hypothesis=True,
            user_hypothesis="milk",
            actual_finding="coffee",
        )

        assert envelope.kind == "specialist_result"
        assert envelope.body["insights"] == insights
        assert envelope.body["contradicts_user_hypothesis"] is True
        assert envelope.body["user_hypothesis"] == "milk"

    def test_create_synthesis_response(self):
        """Test creating synthesis response envelope."""
        conversation_state = {"qud": "What is GERD?", "scoreboard": {}}
        llm_calls = [
            {"operation": "intent_classification", "latency_ms": 28, "cost_usd": 0.0001},
            {"operation": "synthesis", "latency_ms": 185, "cost_usd": 0.001},
        ]

        envelope = EnvelopeFactory.create_synthesis_response(
            user_id="user_123",
            conversation_id="conv_abc",
            trace_id="trace_xyz",
            caused_by="env_result",
            synthesis_text="Interesting - the nutritionist found coffee, not milk",
            specialist_type="nutritionist",
            conversation_state=conversation_state,
            contradiction_detected=True,
            user_assumption="milk",
            actual_finding="coffee",
            llm_calls=llm_calls,
            specialist_duration_ms=850,
        )

        assert envelope.kind == "synthesis_response"
        assert envelope.body["contradiction_detected"] is True
        assert envelope.telemetry["total_latency_ms"] == 28 + 185 + 850
        assert envelope.telemetry["budget_exceeded"] is False


class TestEnvelopeValidator:
    """Test EnvelopeValidator static methods."""

    def test_validate_envelope_success(self):
        """Test successful envelope validation."""
        envelope_dict = {
            "schema_version": "1.0.0",
            "envelope_id": "test_123",
            "ts": "2025-11-08T10:00:00Z",
            "sender": "test.agent",
            "receiver": "user:123",
            "kind": "user_utterance",
            "conversation_id": "conv_123",
            "cognitive_trace_id": "trace_123",
            "body": {"text": "hello"},
        }

        is_valid, errors = EnvelopeValidator.validate_envelope(envelope_dict)

        assert is_valid is True
        assert len(errors) == 0

    def test_validate_envelope_missing_required(self):
        """Test validation fails when required fields missing."""
        envelope_dict = {
            "schema_version": "1.0.0",
            "envelope_id": "test_123",
            # Missing most required fields
        }

        is_valid, errors = EnvelopeValidator.validate_envelope(envelope_dict)

        assert is_valid is False
        assert len(errors) > 0
        assert any("ts" in err for err in errors)
        assert any("sender" in err for err in errors)

    def test_validate_envelope_invalid_proactive_strategy(self):
        """Test validation fails for invalid proactive strategy."""
        envelope_dict = {
            "schema_version": "1.0.0",
            "envelope_id": "test_123",
            "ts": "2025-11-08T10:00:00Z",
            "sender": "concierge.agent",
            "receiver": "user:123",
            "kind": "proactive_prompt",
            "conversation_id": "conv_123",
            "cognitive_trace_id": "trace_123",
            "body": {"strategy": "invalid_strategy", "information_target": "test"},  # Invalid
        }

        is_valid, errors = EnvelopeValidator.validate_envelope(envelope_dict)

        assert is_valid is False
        assert any("Invalid proactive strategy" in err for err in errors)

    def test_validate_envelope_invalid_progress_percent(self):
        """Test validation fails for invalid progress percent."""
        envelope_dict = {
            "schema_version": "1.0.0",
            "envelope_id": "test_123",
            "ts": "2025-11-08T10:00:00Z",
            "sender": "nutritionist.agent",
            "receiver": "concierge.agent",
            "kind": "progress_event",
            "conversation_id": "conv_123",
            "cognitive_trace_id": "trace_123",
            "body": {"milestone": 2, "percent": 150},  # Invalid (>100)
        }

        is_valid, errors = EnvelopeValidator.validate_envelope(envelope_dict)

        assert is_valid is False
        assert any("Invalid percent" in err for err in errors)

    def test_validate_envelope_budget_exceeded(self):
        """Test budget enforcement validation."""
        envelope_dict = {
            "schema_version": "1.0.0",
            "envelope_id": "test_123",
            "ts": "2025-11-08T10:00:00Z",
            "sender": "concierge.agent",
            "receiver": "user:123",
            "kind": "synthesis_response",
            "conversation_id": "conv_123",
            "cognitive_trace_id": "trace_123",
            "telemetry": {"latency_budget_ms": 1200, "total_latency_ms": 1500},
            "body": {"text": "result"},
        }

        is_valid, errors = EnvelopeValidator.validate_envelope(envelope_dict)

        assert is_valid is False
        assert any("Budget exceeded" in err for err in errors)

    def test_validate_envelope_cost_budget_exceeded(self):
        """Test cost budget enforcement."""
        envelope_dict = {
            "schema_version": "1.0.0",
            "envelope_id": "test_123",
            "ts": "2025-11-08T10:00:00Z",
            "sender": "concierge.agent",
            "receiver": "user:123",
            "kind": "synthesis_response",
            "conversation_id": "conv_123",
            "cognitive_trace_id": "trace_123",
            "policy": {"budget_ceiling_usd": 0.10},
            "telemetry": {"total_cost_usd": 0.15},
            "body": {"text": "result"},
        }

        is_valid, errors = EnvelopeValidator.validate_envelope(envelope_dict)

        assert is_valid is False
        assert any("Cost budget exceeded" in err for err in errors)

    def test_validate_envelope_invalid_policy_band(self):
        """Test policy band validation."""
        envelope_dict = {
            "schema_version": "1.0.0",
            "envelope_id": "test_123",
            "ts": "2025-11-08T10:00:00Z",
            "sender": "test.agent",
            "receiver": "user:123",
            "kind": "test",
            "conversation_id": "conv_123",
            "cognitive_trace_id": "trace_123",
            "policy": {"band": "PURPLE"},  # Invalid
        }

        is_valid, errors = EnvelopeValidator.validate_envelope(envelope_dict)

        assert is_valid is False
        assert any("Invalid policy band" in err for err in errors)

    def test_validate_envelope_invalid_capability_format(self):
        """Test capability format validation."""
        envelope_dict = {
            "schema_version": "1.0.0",
            "envelope_id": "test_123",
            "ts": "2025-11-08T10:00:00Z",
            "sender": "test.agent",
            "receiver": "user:123",
            "kind": "test",
            "conversation_id": "conv_123",
            "cognitive_trace_id": "trace_123",
            "policy": {"caps": ["read.k0", "invalid_format"]},  # Missing dot
        }

        is_valid, errors = EnvelopeValidator.validate_envelope(envelope_dict)

        assert is_valid is False
        assert any("Invalid capability format" in err for err in errors)

    def test_validate_envelope_red_band_approval(self):
        """Test RED band requires human approval."""
        envelope_dict = {
            "schema_version": "1.0.0",
            "envelope_id": "test_123",
            "ts": "2025-11-08T10:00:00Z",
            "sender": "test.agent",
            "receiver": "user:123",
            "kind": "test",
            "conversation_id": "conv_123",
            "cognitive_trace_id": "trace_123",
            "policy": {"band": "RED", "human_approval_required": False},  # Should be True for RED
        }

        is_valid, errors = EnvelopeValidator.validate_envelope(envelope_dict)

        assert is_valid is False
        assert any("RED band requires human_approval_required" in err for err in errors)


class TestEnvelopeIntegration:
    """Integration tests for complete envelope workflow."""

    def test_complete_gerd_flow_envelopes(self):
        """Test creating all envelopes for GERD scenario."""
        trace_id = "trace_gerd_123"

        # 1. User utterance
        user_env = EnvelopeFactory.create_user_utterance(
            user_id="user_123",
            conversation_id="conv_abc",
            text="milk is making me sick",
            trace_id=trace_id,
        )
        assert user_env.validate()[0] is True

        # 2. Reactive response
        reactive_env = EnvelopeFactory.create_reactive_response(
            user_id="user_123",
            conversation_id="conv_abc",
            trace_id=trace_id,
            caused_by=user_env.envelope_id,
            intent={"type": "QUERY", "domain": "health", "confidence": 0.92},
            conversation_state={"qud": "What causes GERD?", "scoreboard": {}},
            affect={"label": "concerned", "confidence": 0.8},
            empathy_text="That's sad to hear",
            action_declaration="Looping in nutritionist",
            llm_calls=[{"operation": "intent", "latency_ms": 28, "cost_usd": 0.0001}],
        )
        assert reactive_env.validate()[0] is True

        # 3. Proactive prompt
        proactive_env = EnvelopeFactory.create_proactive_prompt(
            user_id="user_123",
            conversation_id="conv_abc",
            trace_id=trace_id,
            caused_by=user_env.envelope_id,
            prompt_text="Until nutritionist gathers data, how severe is the pain?",
            strategy="fill_gap",
            information_target="pain_severity",
            information_gaps=["pain_severity"],
            conversation_state={"qud": "What causes GERD?"},
            llm_calls=[{"operation": "gap", "latency_ms": 45, "cost_usd": 0.0002}],
        )
        assert proactive_env.validate()[0] is True

        # 4. Specialist result
        result_env = EnvelopeFactory.create_specialist_result(
            specialist_type="nutritionist",
            conversation_id="conv_abc",
            trace_id=trace_id,
            task_id="task_123",
            caused_by="spawn_env",
            query="What triggers GERD?",
            insights=[{"summary": "Coffee is trigger", "confidence": 0.85}],
            evidence=["Pattern data"],
            confidence=0.85,
            duration_ms=850,
            contradicts_user_hypothesis=True,
            user_hypothesis="milk",
            actual_finding="coffee",
        )
        assert result_env.validate()[0] is True

        # Verify envelope chain
        assert reactive_env.caused_by[0] == user_env.envelope_id
        assert proactive_env.caused_by[0] == user_env.envelope_id
        assert all(
            env.cognitive_trace_id == trace_id
            for env in [user_env, reactive_env, proactive_env, result_env]
        )
