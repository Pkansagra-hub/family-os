"""
Tests for Epic 3.2: Scheduler Integration

Tests for:
- Issue 3.2.1: Scheduler integration into app bootstrap
- Issue 3.2.2: PipelineLoadResult and YAML loader
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from k0.pipelines.loader import PipelineLoadResult, load_yaml_pipeline_specs
from k0.scheduler import (
    PipelineScheduler,
    get_pipeline_scheduler,
    reset_pipeline_scheduler,
    set_pipeline_scheduler,
)

# ============================================================
# PipelineLoadResult Tests (Issue 3.2.2)
# ============================================================


class TestPipelineLoadResult:
    """Tests for PipelineLoadResult dataclass."""

    def test_load_result_default_values(self) -> None:
        """Test default values for PipelineLoadResult."""
        result = PipelineLoadResult()

        assert result.loaded_count == 0
        assert result.specs == []
        assert result.runners == {}
        assert result.errors == []

    def test_load_result_with_values(self) -> None:
        """Test PipelineLoadResult with populated values."""
        mock_spec = MagicMock()
        mock_spec.pipeline_id = "test_pipeline"

        result = PipelineLoadResult(
            loaded_count=1,
            specs=[mock_spec],
            runners={"test_pipeline": MagicMock()},
            errors=["Some error"],
        )

        assert result.loaded_count == 1
        assert len(result.specs) == 1
        assert "test_pipeline" in result.runners
        assert len(result.errors) == 1

    def test_load_result_mutable_fields(self) -> None:
        """Test that fields can be modified after creation."""
        result = PipelineLoadResult()

        result.loaded_count += 1
        result.specs.append(MagicMock())
        result.errors.append("test error")

        assert result.loaded_count == 1
        assert len(result.specs) == 1
        assert len(result.errors) == 1


# ============================================================
# Scheduler Singleton Tests (Issue 3.2.1)
# ============================================================


class TestSchedulerSingleton:
    """Tests for scheduler singleton pattern."""

    def teardown_method(self) -> None:
        """Reset scheduler after each test."""
        reset_pipeline_scheduler()

    def test_get_scheduler_returns_none_initially(self) -> None:
        """Test that get_pipeline_scheduler returns None initially."""
        assert get_pipeline_scheduler() is None

    def test_set_scheduler_stores_instance(self) -> None:
        """Test that set_pipeline_scheduler stores the instance."""
        mock_syscalls = MagicMock()
        scheduler = PipelineScheduler(mock_syscalls)

        set_pipeline_scheduler(scheduler)

        assert get_pipeline_scheduler() is scheduler

    def test_reset_scheduler_clears_instance(self) -> None:
        """Test that reset_pipeline_scheduler clears the instance."""
        mock_syscalls = MagicMock()
        scheduler = PipelineScheduler(mock_syscalls)
        set_pipeline_scheduler(scheduler)

        reset_pipeline_scheduler()

        assert get_pipeline_scheduler() is None


# ============================================================
# YAML Pipeline Loader Tests (Issue 3.2.2)
# ============================================================


class TestLoadYamlPipelineSpecs:
    """Tests for load_yaml_pipeline_specs function."""

    @pytest.mark.asyncio
    async def test_load_missing_directory_returns_error(self, tmp_path: Path) -> None:
        """Test loading from non-existent directory."""
        missing_dir = tmp_path / "nonexistent"

        result = await load_yaml_pipeline_specs(missing_dir)

        assert result.loaded_count == 0
        assert len(result.errors) == 1
        assert "not found" in result.errors[0]

    @pytest.mark.asyncio
    async def test_load_empty_directory(self, tmp_path: Path) -> None:
        """Test loading from empty directory."""
        result = await load_yaml_pipeline_specs(tmp_path)

        assert result.loaded_count == 0
        assert result.specs == []
        assert result.errors == []

    @pytest.mark.asyncio
    async def test_load_valid_yaml_spec(self, tmp_path: Path) -> None:
        """Test loading valid YAML pipeline spec."""
        # Create a minimal valid pipeline YAML
        # Module pattern: namespace.module:version
        spec_content = """
id: p99_test
version: v1
pipeline_id: P99_TEST
dag:
  - id: stage1
    module: test.handler:v1
    after: []
declared_topics:
  - test.topic
"""
        spec_file = tmp_path / "p99_test.yaml"
        spec_file.write_text(spec_content)

        result = await load_yaml_pipeline_specs(tmp_path)

        assert result.loaded_count == 1
        assert len(result.specs) == 1
        assert result.specs[0].pipeline_id == "P99_TEST"

    @pytest.mark.asyncio
    async def test_load_invalid_yaml_captured_in_errors(self, tmp_path: Path) -> None:
        """Test that invalid YAML is captured in errors."""
        # Create invalid YAML
        spec_file = tmp_path / "p99_bad.yaml"
        spec_file.write_text("invalid: [yaml: content")

        result = await load_yaml_pipeline_specs(tmp_path)

        assert result.loaded_count == 0
        assert len(result.errors) == 1
        assert "p99_bad.yaml" in result.errors[0]

    @pytest.mark.asyncio
    async def test_load_multiple_specs(self, tmp_path: Path) -> None:
        """Test loading multiple pipeline specs."""
        for i in range(3):
            spec_content = f"""
id: p{i:02d}_test
version: v1
pipeline_id: P{i:02d}_TEST
dag:
  - id: stage1
    module: test.handler:v1
    after: []
declared_topics:
  - test.topic
"""
            spec_file = tmp_path / f"p{i:02d}_test.yaml"
            spec_file.write_text(spec_content)

        result = await load_yaml_pipeline_specs(tmp_path)

        assert result.loaded_count == 3
        assert len(result.specs) == 3

    @pytest.mark.asyncio
    async def test_load_specs_with_triggers(self, tmp_path: Path) -> None:
        """Test loading spec with trigger configuration."""
        spec_content = """
id: p99_triggered
version: v1
pipeline_id: P99_TRIGGERED
dag:
  - id: stage1
    module: test.handler:v1
    after: []
declared_topics:
  - test.topic
triggers:
  - id: interval_trigger
    type: interval
    interval_seconds: 60
  - id: manual_trigger
    type: manual
"""
        spec_file = tmp_path / "p99_triggered.yaml"
        spec_file.write_text(spec_content)

        result = await load_yaml_pipeline_specs(tmp_path)

        assert result.loaded_count == 1
        spec = result.specs[0]
        assert len(spec.triggers) == 2
        assert spec.triggers[0].id == "interval_trigger"
        assert spec.triggers[1].id == "manual_trigger"
