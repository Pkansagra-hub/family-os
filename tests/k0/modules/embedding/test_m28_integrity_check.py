"""Integration tests for M28 embedding.integrity_check -- health validation.

Exercises the real M28 module code against FakeSyscalls.
Validates 4 diagnostic checks, health classification (HEALTHY/DEGRADED/CRITICAL),
and auto-correction of missing vectors.

Epic: M4 4.21
Module: k0/modules/embedding/integrity_check.py
Contract: k0/contracts/modules/embedding.integrity_check.v1.yaml
"""

from __future__ import annotations

from typing import Any

import pytest

from k0.modules.embedding import integrity_check
from tests.k0.modules.embedding.conftest import FakeContext, FakeMessage, FakeSyscalls


@pytest.fixture(autouse=True)
def _reset_integrity_metrics() -> None:
    """Reset M28 metrics before each test."""
    integrity_check.reset_metrics()


# =============================================================================
# Test Class 1: HEALTHY State -- No Issues
# =============================================================================


class TestM28Healthy:
    """M28 reports HEALTHY when all vectors are consistent."""

    @pytest.mark.asyncio
    async def test_healthy_status(
        self,
        syscalls: FakeSyscalls,
        context: FakeContext,
        message: FakeMessage,
        sample_vectors: list[dict[str, Any]],
    ) -> None:
        result = await integrity_check.run(message, context)

        report = result["integrity_check"]
        assert report["status"] == "HEALTHY"

    @pytest.mark.asyncio
    async def test_healthy_total_vectors(
        self,
        syscalls: FakeSyscalls,
        context: FakeContext,
        message: FakeMessage,
        sample_vectors: list[dict[str, Any]],
    ) -> None:
        result = await integrity_check.run(message, context)

        report = result["integrity_check"]
        assert report["total_vectors"] == 3

    @pytest.mark.asyncio
    async def test_healthy_zero_issues(
        self,
        syscalls: FakeSyscalls,
        context: FakeContext,
        message: FakeMessage,
        sample_vectors: list[dict[str, Any]],
    ) -> None:
        result = await integrity_check.run(message, context)

        report = result["integrity_check"]
        assert report["dimension_mismatches"] == 0
        assert report["orphaned_vectors"] == 0
        assert report["missing_vectors"] == 0
        assert report["auto_corrected"] == 0

    @pytest.mark.asyncio
    async def test_healthy_checked_at_present(
        self,
        syscalls: FakeSyscalls,
        context: FakeContext,
        message: FakeMessage,
        sample_vectors: list[dict[str, Any]],
    ) -> None:
        result = await integrity_check.run(message, context)

        report = result["integrity_check"]
        assert report["checked_at"] != ""

    @pytest.mark.asyncio
    async def test_healthy_metric(
        self,
        syscalls: FakeSyscalls,
        context: FakeContext,
        message: FakeMessage,
        sample_vectors: list[dict[str, Any]],
    ) -> None:
        await integrity_check.run(message, context)

        metrics = integrity_check.get_metrics()
        assert metrics["healthy_count"] == 1
        assert metrics["checks_run"] == 1


# =============================================================================
# Test Class 2: DEGRADED State -- Some Issues Below Threshold
# =============================================================================


class TestM28Degraded:
    """M28 reports DEGRADED when issues exist but below threshold."""

    @pytest.mark.asyncio
    async def test_degraded_with_orphans(
        self,
        syscalls: FakeSyscalls,
        context: FakeContext,
        message: FakeMessage,
        sample_vectors: list[dict[str, Any]],
    ) -> None:
        # Add 5 orphaned vectors (event_id not in hipp_events)
        for i in range(5):
            syscalls.vec_store[f"orphan_{i}"] = {
                "embedding_id": f"orphan_{i}",
                "event_id": f"deleted_evt_{i}",
                "tenant_id": "tenant_test",
                "space_id": "space_home",
                "vector": [0.01] * 768,
                "vector_dim": 768,
                "model_id": "ultrabert_v2.1.0",
                "status": "READY",
            }

        result = await integrity_check.run(message, context)

        report = result["integrity_check"]
        assert report["status"] == "DEGRADED"
        assert report["orphaned_vectors"] == 5

    @pytest.mark.asyncio
    async def test_degraded_with_dimension_mismatch(
        self,
        syscalls: FakeSyscalls,
        context: FakeContext,
        message: FakeMessage,
        sample_vectors: list[dict[str, Any]],
    ) -> None:
        # Add a vector with wrong dimension
        syscalls.hipp_events["evt_bad_dim"] = {
            "event_id": "evt_bad_dim",
            "tenant_id": "tenant_test",
            "space_id": "space_home",
            "embedding_status": "READY",
        }
        syscalls.vec_store["emb_bad_dim"] = {
            "embedding_id": "emb_bad_dim",
            "event_id": "evt_bad_dim",
            "tenant_id": "tenant_test",
            "space_id": "space_home",
            "vector": [0.01] * 384,  # wrong dimension
            "vector_dim": 384,
            "model_id": "minilm_v1.0",
            "status": "READY",
        }

        result = await integrity_check.run(message, context)

        report = result["integrity_check"]
        assert report["dimension_mismatches"] == 1

    @pytest.mark.asyncio
    async def test_degraded_metric(
        self,
        syscalls: FakeSyscalls,
        context: FakeContext,
        message: FakeMessage,
        sample_vectors: list[dict[str, Any]],
    ) -> None:
        # Add a few orphans to trigger DEGRADED
        for i in range(3):
            syscalls.vec_store[f"orphan_{i}"] = {
                "embedding_id": f"orphan_{i}",
                "event_id": f"deleted_{i}",
                "tenant_id": "tenant_test",
                "space_id": "space_home",
                "vector": [0.01] * 768,
                "vector_dim": 768,
                "model_id": "ultrabert_v2.1.0",
                "status": "READY",
            }

        await integrity_check.run(message, context)

        metrics = integrity_check.get_metrics()
        assert metrics["degraded_count"] == 1


# =============================================================================
# Test Class 3: CRITICAL State -- Issues Exceed Threshold
# =============================================================================


class TestM28Critical:
    """M28 reports CRITICAL when total issues >= degraded_threshold."""

    @pytest.mark.asyncio
    async def test_critical_with_many_orphans(
        self,
        syscalls: FakeSyscalls,
        context: FakeContext,
        message: FakeMessage,
    ) -> None:
        # Seed 150 orphans (exceeds default threshold of 100)
        for i in range(150):
            syscalls.vec_store[f"orphan_{i}"] = {
                "embedding_id": f"orphan_{i}",
                "event_id": f"gone_evt_{i}",
                "tenant_id": "tenant_test",
                "space_id": "space_home",
                "vector": [0.01] * 768,
                "vector_dim": 768,
                "model_id": "ultrabert_v2.1.0",
                "status": "READY",
            }

        result = await integrity_check.run(message, context)

        report = result["integrity_check"]
        assert report["status"] == "CRITICAL"
        assert report["orphaned_vectors"] == 150

    @pytest.mark.asyncio
    async def test_custom_threshold(
        self,
        syscalls: FakeSyscalls,
        context: FakeContext,
        message: FakeMessage,
    ) -> None:
        # 5 orphans with low threshold=3 -> CRITICAL
        for i in range(5):
            syscalls.vec_store[f"orphan_{i}"] = {
                "embedding_id": f"orphan_{i}",
                "event_id": f"gone_{i}",
                "tenant_id": "tenant_test",
                "space_id": "space_home",
                "vector": [0.01] * 768,
                "vector_dim": 768,
                "model_id": "ultrabert_v2.1.0",
                "status": "READY",
            }

        result = await integrity_check.run(message, context, degraded_threshold=3)

        report = result["integrity_check"]
        assert report["status"] == "CRITICAL"


# =============================================================================
# Test Class 4: Auto-Correction of Missing Vectors
# =============================================================================


class TestM28AutoCorrection:
    """M28 resets embedding_status=PENDING for events with missing st_vec rows."""

    @pytest.mark.asyncio
    async def test_auto_correct_missing_vectors(
        self,
        syscalls: FakeSyscalls,
        context: FakeContext,
        message: FakeMessage,
    ) -> None:
        # Events marked READY but no corresponding st_vec row
        for i in range(3):
            syscalls.hipp_events[f"evt_missing_{i}"] = {
                "event_id": f"evt_missing_{i}",
                "tenant_id": "tenant_test",
                "space_id": "space_home",
                "embedding_status": "READY",
            }

        result = await integrity_check.run(message, context, auto_correct_missing=True)

        report = result["integrity_check"]
        assert report["missing_vectors"] == 3
        assert report["auto_corrected"] == 3

        # Verify status reset to PENDING
        for i in range(3):
            assert syscalls.hipp_events[f"evt_missing_{i}"]["embedding_status"] == "PENDING"

    @pytest.mark.asyncio
    async def test_no_auto_correct_when_disabled(
        self,
        syscalls: FakeSyscalls,
        context: FakeContext,
        message: FakeMessage,
    ) -> None:
        syscalls.hipp_events["evt_missing_0"] = {
            "event_id": "evt_missing_0",
            "tenant_id": "tenant_test",
            "space_id": "space_home",
            "embedding_status": "READY",
        }

        result = await integrity_check.run(message, context, auto_correct_missing=False)

        report = result["integrity_check"]
        assert report["missing_vectors"] == 1
        assert report["auto_corrected"] == 0
        assert syscalls.hipp_events["evt_missing_0"]["embedding_status"] == "READY"


# =============================================================================
# Test Class 5: Model Consistency Check
# =============================================================================


class TestM28ModelConsistency:
    """M28 detects mixed model versions in st_vec."""

    @pytest.mark.asyncio
    async def test_single_model_consistent(
        self,
        syscalls: FakeSyscalls,
        context: FakeContext,
        message: FakeMessage,
        sample_vectors: list[dict[str, Any]],
    ) -> None:
        result = await integrity_check.run(message, context)

        report = result["integrity_check"]
        assert len(report["model_versions"]) == 1
        assert "ultrabert_v2.1.0" in report["model_versions"]

    @pytest.mark.asyncio
    async def test_multiple_models_detected(
        self,
        syscalls: FakeSyscalls,
        context: FakeContext,
        message: FakeMessage,
        sample_vectors: list[dict[str, Any]],
    ) -> None:
        # Add a vector with a different model
        syscalls.hipp_events["evt_old_model"] = {
            "event_id": "evt_old_model",
            "tenant_id": "tenant_test",
            "space_id": "space_home",
            "embedding_status": "READY",
        }
        syscalls.vec_store["emb_old_model"] = {
            "embedding_id": "emb_old_model",
            "event_id": "evt_old_model",
            "tenant_id": "tenant_test",
            "space_id": "space_home",
            "vector": [0.01] * 768,
            "vector_dim": 768,
            "model_id": "minilm_v1.0",
            "status": "READY",
        }

        result = await integrity_check.run(message, context)

        report = result["integrity_check"]
        assert len(report["model_versions"]) == 2


# =============================================================================
# Test Class 6: Return Value Contract
# =============================================================================


class TestM28ReturnContract:
    """M28 return dict matches integrity_check module contract."""

    @pytest.mark.asyncio
    async def test_return_has_integrity_check_key(
        self,
        context: FakeContext,
        message: FakeMessage,
    ) -> None:
        result = await integrity_check.run(message, context)
        assert "integrity_check" in result

    @pytest.mark.asyncio
    async def test_return_report_keys(
        self,
        context: FakeContext,
        message: FakeMessage,
    ) -> None:
        result = await integrity_check.run(message, context)
        report = result["integrity_check"]

        expected_keys = {
            "total_vectors",
            "dimension_mismatches",
            "model_versions",
            "orphaned_vectors",
            "missing_vectors",
            "auto_corrected",
            "status",
            "checked_at",
        }
        assert expected_keys == set(report.keys())

    @pytest.mark.asyncio
    async def test_status_is_valid_enum(
        self,
        context: FakeContext,
        message: FakeMessage,
    ) -> None:
        result = await integrity_check.run(message, context)
        report = result["integrity_check"]
        assert report["status"] in {"HEALTHY", "DEGRADED", "CRITICAL"}
