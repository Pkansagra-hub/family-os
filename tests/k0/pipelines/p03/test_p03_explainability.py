"""
Test suite for P03 Explainability Service.

Tests the explainability query API which provides user-safe
explanations for consolidation decisions.

Spec Reference: Dossier §14.10 Explainability Templates
"""

from __future__ import annotations

import time
import uuid

import pytest

from k0.pipelines.p03.explainability import (
    DEFAULT_EXPLANATION,
    ExplainabilityService,
    InMemoryAuditRepository,
    MemoryExplanation,
    create_explainability_service,
    get_default_explanation,
)

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def repository() -> InMemoryAuditRepository:
    """Create a fresh in-memory repository."""
    return InMemoryAuditRepository()


@pytest.fixture
def service(repository: InMemoryAuditRepository) -> ExplainabilityService:
    """Create an explainability service with the test repository."""
    return ExplainabilityService(repository)


@pytest.fixture
def sample_audit_record() -> dict:
    """Create a sample audit record."""
    return {
        "audit_id": str(uuid.uuid4()),
        "memory_id": "mem_001",
        "space_id": "space_1",
        "tenant_id": "tenant_1",
        "action": "REINFORCE",
        "explanation": "Memory was reinforced because it matched recent context with high similarity.",
        "confidence": 0.85,
        "created_at": int(time.time() * 1000),
        "source_table": "st_epi",
        "formula_used": "cosine_similarity",
        "cycle_id": "cycle_001",
    }


# =============================================================================
# TEST CLASS: MemoryExplanation Dataclass
# =============================================================================


class TestMemoryExplanation:
    """Tests for the MemoryExplanation dataclass."""

    def test_memory_explanation_creation(self):
        """Test creating a MemoryExplanation with all fields."""
        explanation = MemoryExplanation(
            memory_id="mem_001",
            action="REINFORCE",
            explanation="Test explanation",
            confidence=0.9,
            created_at=1234567890000,
            source_table="st_epi",
            formula_used="cosine_similarity",
            cycle_id="cycle_001",
        )

        assert explanation.memory_id == "mem_001"
        assert explanation.action == "REINFORCE"
        assert explanation.explanation == "Test explanation"
        assert explanation.confidence == 0.9
        assert explanation.created_at == 1234567890000
        assert explanation.source_table == "st_epi"
        assert explanation.formula_used == "cosine_similarity"
        assert explanation.cycle_id == "cycle_001"

    def test_memory_explanation_optional_fields(self):
        """Test MemoryExplanation with optional fields defaulting to None."""
        explanation = MemoryExplanation(
            memory_id="mem_001",
            action="SKIP",
            explanation="Skipped",
            confidence=None,
            created_at=1234567890000,
        )

        assert explanation.source_table is None
        assert explanation.formula_used is None
        assert explanation.cycle_id is None

    def test_memory_explanation_is_frozen(self):
        """Test that MemoryExplanation is immutable."""
        explanation = MemoryExplanation(
            memory_id="mem_001",
            action="REINFORCE",
            explanation="Test",
            confidence=0.9,
            created_at=1234567890000,
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            explanation.memory_id = "different"  # type: ignore

    def test_memory_explanation_to_dict(self):
        """Test converting MemoryExplanation to dictionary."""
        explanation = MemoryExplanation(
            memory_id="mem_001",
            action="REINFORCE",
            explanation="Test explanation",
            confidence=0.85,
            created_at=1234567890000,
            source_table="st_epi",
            formula_used="cosine_similarity",
            cycle_id="cycle_001",
        )

        result = explanation.to_dict()

        assert result["memory_id"] == "mem_001"
        assert result["action"] == "REINFORCE"
        assert result["explanation"] == "Test explanation"
        assert result["confidence"] == 0.85
        assert result["source_table"] == "st_epi"


# =============================================================================
# TEST CLASS: DEFAULT_EXPLANATION
# =============================================================================


class TestDefaultExplanation:
    """Tests for the default explanation constant and helper."""

    def test_default_explanation_constant(self):
        """Test DEFAULT_EXPLANATION has expected structure."""
        assert "No consolidation decision" in DEFAULT_EXPLANATION
        assert isinstance(DEFAULT_EXPLANATION, str)

    def test_get_default_explanation_creates_new_instance(self):
        """Test get_default_explanation creates proper explanation."""
        explanation = get_default_explanation("mem_123")

        assert explanation.memory_id == "mem_123"
        assert explanation.action == "UNKNOWN"
        assert "No consolidation decision" in explanation.explanation
        assert explanation.confidence is None

    def test_get_default_explanation_has_zero_timestamp(self):
        """Test that default explanation has zero timestamp (no record found)."""
        explanation = get_default_explanation("mem_123")

        # Default explanations have created_at=0 since no record exists
        assert explanation.created_at == 0


# =============================================================================
# TEST CLASS: InMemoryAuditRepository
# =============================================================================


class TestInMemoryAuditRepository:
    """Tests for the in-memory audit repository."""

    def test_repository_starts_empty(self, repository: InMemoryAuditRepository):
        """Test repository starts with no records."""
        records = repository.get_audit_history_for_memory(
            memory_id="mem_001",
            space_id="space_1",
            tenant_id="tenant_1",
        )
        assert records == []

    def test_add_and_retrieve_record(
        self,
        repository: InMemoryAuditRepository,
        sample_audit_record: dict,
    ):
        """Test adding and retrieving a record."""
        repository.add_record(sample_audit_record)

        records = repository.get_audit_history_for_memory(
            memory_id="mem_001",
            space_id="space_1",
            tenant_id="tenant_1",
        )

        assert len(records) == 1
        assert records[0]["memory_id"] == "mem_001"
        assert records[0]["action"] == "REINFORCE"

    def test_get_latest_record(
        self,
        repository: InMemoryAuditRepository,
    ):
        """Test retrieving the most recent record."""
        # Add older record
        repository.add_record(
            {
                "audit_id": "audit_1",
                "memory_id": "mem_001",
                "space_id": "space_1",
                "tenant_id": "tenant_1",
                "action": "CREATE",
                "explanation": "Initial creation",
                "created_at": 1000,
            }
        )

        # Add newer record
        repository.add_record(
            {
                "audit_id": "audit_2",
                "memory_id": "mem_001",
                "space_id": "space_1",
                "tenant_id": "tenant_1",
                "action": "REINFORCE",
                "explanation": "Reinforced",
                "created_at": 2000,
            }
        )

        latest = repository.get_latest_audit_for_memory(
            memory_id="mem_001",
            space_id="space_1",
            tenant_id="tenant_1",
        )

        assert latest is not None
        assert latest["action"] == "REINFORCE"
        assert latest["created_at"] == 2000

    def test_get_latest_record_returns_none_when_empty(
        self,
        repository: InMemoryAuditRepository,
    ):
        """Test get_latest_audit_for_memory returns None when no records."""
        latest = repository.get_latest_audit_for_memory(
            memory_id="mem_nonexistent",
            space_id="space_1",
            tenant_id="tenant_1",
        )

        assert latest is None

    def test_tenant_isolation(
        self,
        repository: InMemoryAuditRepository,
        sample_audit_record: dict,
    ):
        """Test records are isolated by tenant."""
        repository.add_record(sample_audit_record)

        # Same memory_id but different tenant
        records = repository.get_audit_history_for_memory(
            memory_id="mem_001",
            space_id="space_1",
            tenant_id="different_tenant",
        )

        assert records == []

    def test_space_isolation(
        self,
        repository: InMemoryAuditRepository,
        sample_audit_record: dict,
    ):
        """Test records are isolated by space."""
        repository.add_record(sample_audit_record)

        # Same memory_id but different space
        records = repository.get_audit_history_for_memory(
            memory_id="mem_001",
            space_id="different_space",
            tenant_id="tenant_1",
        )

        assert records == []

    def test_clear_repository(
        self,
        repository: InMemoryAuditRepository,
        sample_audit_record: dict,
    ):
        """Test clearing all records from repository."""
        repository.add_record(sample_audit_record)
        repository.clear()

        records = repository.get_audit_history_for_memory(
            memory_id="mem_001",
            space_id="space_1",
            tenant_id="tenant_1",
        )

        assert records == []

    def test_limit_parameter(self, repository: InMemoryAuditRepository):
        """Test limit parameter on get_audit_history_for_memory."""
        # Add multiple records
        for i in range(5):
            repository.add_record(
                {
                    "audit_id": f"audit_{i}",
                    "memory_id": "mem_001",
                    "space_id": "space_1",
                    "tenant_id": "tenant_1",
                    "action": "REINFORCE",
                    "explanation": f"Explanation {i}",
                    "created_at": i * 1000,
                }
            )

        records = repository.get_audit_history_for_memory(
            memory_id="mem_001",
            space_id="space_1",
            tenant_id="tenant_1",
            limit=3,
        )

        assert len(records) == 3


# =============================================================================
# TEST CLASS: ExplainabilityService
# =============================================================================


class TestExplainabilityService:
    """Tests for the ExplainabilityService."""

    def test_explain_memory_with_no_record(
        self,
        service: ExplainabilityService,
    ):
        """Test explaining a memory with no audit record returns default."""
        result = service.explain_memory(
            memory_id="nonexistent",
            space_id="space_1",
            tenant_id="tenant_1",
        )

        assert result.memory_id == "nonexistent"
        assert result.action == "UNKNOWN"
        assert "No consolidation decision" in result.explanation

    def test_explain_memory_with_record(
        self,
        repository: InMemoryAuditRepository,
        service: ExplainabilityService,
        sample_audit_record: dict,
    ):
        """Test explaining a memory with existing audit record."""
        repository.add_record(sample_audit_record)

        result = service.explain_memory(
            memory_id="mem_001",
            space_id="space_1",
            tenant_id="tenant_1",
        )

        assert result.memory_id == "mem_001"
        assert result.action == "REINFORCE"
        assert result.explanation == sample_audit_record["explanation"]
        assert result.confidence == 0.85
        assert result.source_table == "st_epi"
        assert result.formula_used == "cosine_similarity"

    def test_explain_memory_cross_space_returns_default(
        self,
        repository: InMemoryAuditRepository,
        service: ExplainabilityService,
        sample_audit_record: dict,
    ):
        """Test explaining memory from different space returns default."""
        repository.add_record(sample_audit_record)

        # Query with different space
        result = service.explain_memory(
            memory_id="mem_001",
            space_id="other_space",
            tenant_id="tenant_1",
        )

        assert result.action == "UNKNOWN"

    def test_explain_memory_cross_tenant_returns_default(
        self,
        repository: InMemoryAuditRepository,
        service: ExplainabilityService,
        sample_audit_record: dict,
    ):
        """Test explaining memory from different tenant returns default."""
        repository.add_record(sample_audit_record)

        # Query with different tenant
        result = service.explain_memory(
            memory_id="mem_001",
            space_id="space_1",
            tenant_id="other_tenant",
        )

        assert result.action == "UNKNOWN"

    def test_get_memory_history_empty(
        self,
        service: ExplainabilityService,
    ):
        """Test getting history for memory with no records."""
        history = service.get_memory_history(
            memory_id="nonexistent",
            space_id="space_1",
            tenant_id="tenant_1",
        )

        assert history == []

    def test_get_memory_history_multiple_records(
        self,
        repository: InMemoryAuditRepository,
        service: ExplainabilityService,
    ):
        """Test getting history with multiple records."""
        # Add multiple actions for same memory
        for i, action in enumerate(["CREATE", "REINFORCE", "DECAY"]):
            repository.add_record(
                {
                    "audit_id": f"audit_{i}",
                    "memory_id": "mem_001",
                    "space_id": "space_1",
                    "tenant_id": "tenant_1",
                    "action": action,
                    "explanation": f"Action: {action}",
                    "created_at": i * 1000,
                }
            )

        history = service.get_memory_history(
            memory_id="mem_001",
            space_id="space_1",
            tenant_id="tenant_1",
        )

        assert len(history) == 3
        # Verify they are MemoryExplanation objects
        assert all(isinstance(h, MemoryExplanation) for h in history)

    def test_get_memory_history_respects_limit(
        self,
        repository: InMemoryAuditRepository,
        service: ExplainabilityService,
    ):
        """Test history retrieval respects limit parameter."""
        # Add 10 records
        for i in range(10):
            repository.add_record(
                {
                    "audit_id": f"audit_{i}",
                    "memory_id": "mem_001",
                    "space_id": "space_1",
                    "tenant_id": "tenant_1",
                    "action": "REINFORCE",
                    "explanation": f"Reinforcement {i}",
                    "created_at": i * 1000,
                }
            )

        history = service.get_memory_history(
            memory_id="mem_001",
            space_id="space_1",
            tenant_id="tenant_1",
            limit=5,
        )

        assert len(history) == 5


# =============================================================================
# TEST CLASS: Factory Function
# =============================================================================


class TestFactoryFunction:
    """Tests for the factory function."""

    def test_create_explainability_service(
        self,
        repository: InMemoryAuditRepository,
    ):
        """Test creating service via factory function."""
        service = create_explainability_service(repository)

        assert isinstance(service, ExplainabilityService)

    def test_created_service_is_functional(
        self,
        repository: InMemoryAuditRepository,
    ):
        """Test service created by factory is fully functional."""
        service = create_explainability_service(repository)

        repository.add_record(
            {
                "audit_id": "test_audit",
                "memory_id": "mem_001",
                "space_id": "space_1",
                "tenant_id": "tenant_1",
                "action": "CREATE",
                "explanation": "Memory created",
                "created_at": 1000,
            }
        )

        result = service.explain_memory(
            memory_id="mem_001",
            space_id="space_1",
            tenant_id="tenant_1",
        )

        assert result.action == "CREATE"


# =============================================================================
# TEST CLASS: Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_memory_id(
        self,
        service: ExplainabilityService,
    ):
        """Test handling empty memory_id."""
        result = service.explain_memory(
            memory_id="",
            space_id="space_1",
            tenant_id="tenant_1",
        )

        # Should return default explanation
        assert result.action == "UNKNOWN"

    def test_special_characters_in_ids(
        self,
        repository: InMemoryAuditRepository,
        service: ExplainabilityService,
    ):
        """Test handling special characters in IDs."""
        special_id = "mem:001/sub?query=test"
        repository.add_record(
            {
                "audit_id": "audit_special",
                "memory_id": special_id,
                "space_id": "space_1",
                "tenant_id": "tenant_1",
                "action": "CREATE",
                "explanation": "Created with special ID",
                "created_at": 1000,
            }
        )

        result = service.explain_memory(
            memory_id=special_id,
            space_id="space_1",
            tenant_id="tenant_1",
        )

        assert result.action == "CREATE"

    def test_very_long_explanation(
        self,
        repository: InMemoryAuditRepository,
        service: ExplainabilityService,
    ):
        """Test handling very long explanation text."""
        long_explanation = "A" * 10000
        repository.add_record(
            {
                "audit_id": "audit_long",
                "memory_id": "mem_001",
                "space_id": "space_1",
                "tenant_id": "tenant_1",
                "action": "REINFORCE",
                "explanation": long_explanation,
                "created_at": 1000,
            }
        )

        result = service.explain_memory(
            memory_id="mem_001",
            space_id="space_1",
            tenant_id="tenant_1",
        )

        assert len(result.explanation) == 10000

    def test_null_confidence_handling(
        self,
        repository: InMemoryAuditRepository,
        service: ExplainabilityService,
    ):
        """Test handling null/None confidence values."""
        repository.add_record(
            {
                "audit_id": "audit_null_conf",
                "memory_id": "mem_001",
                "space_id": "space_1",
                "tenant_id": "tenant_1",
                "action": "SKIP",
                "explanation": "Skipped - no confidence",
                "confidence": None,
                "created_at": 1000,
            }
        )

        result = service.explain_memory(
            memory_id="mem_001",
            space_id="space_1",
            tenant_id="tenant_1",
        )

        assert result.confidence is None
