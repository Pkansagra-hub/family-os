"""
Integration tests for pipeline loader integration into kernel boot sequence.

Tests M2 R2.3: Kernel Integration
- Pipeline discovery during startup
- Graceful shutdown with on_shutdown() calls
- Clean shutdown timestamp recording
- Empty pipeline directory handling
"""

import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestKernelPipelineIntegration:
    """Integration tests for kernel + pipeline loader."""

    @pytest.mark.asyncio
    async def test_kernel_boots_with_empty_pipelines_directory(self, tmp_path: Path):
        """Test: Kernel boots successfully with empty pipelines directory."""
        # This test verifies that the kernel doesn't crash when no pipelines exist
        # We'll mock the discover_and_boot_pipelines to return empty dict

        from k0.kernel.app import create_app
        from k0.kernel.config import DatabaseSettings, KernelSettings, ServerSettings

        # Create minimal settings
        db_path = tmp_path / "test.db"
        settings = KernelSettings(
            database=DatabaseSettings(path=db_path),
            server=ServerSettings(host="127.0.0.1", port=8000),
        )

        # Mock discover_and_boot_pipelines at import location
        with patch("k0.pipelines.loader.discover_and_boot_pipelines") as mock_discover:
            mock_discover.return_value = {}

            # Create app (this triggers lifespan startup)
            app = create_app(settings)

            # Verify app was created successfully
            assert app is not None
            assert hasattr(app.state, "pipelines")

            # Start lifespan to trigger pipeline loading
            async with app.router.lifespan_context(app):
                # Verify pipelines were loaded (empty dict)
                assert app.state.pipelines == {}

                # Verify discover_and_boot_pipelines was called
                assert mock_discover.called
                call_kwargs = mock_discover.call_args.kwargs
                assert "bus_dispatcher" in call_kwargs
                assert "uow_factory" in call_kwargs
                assert "config" in call_kwargs
                assert "logger" in call_kwargs

    @pytest.mark.asyncio
    async def test_kernel_boots_with_valid_pipeline(self, tmp_path: Path):
        """Test: Kernel boots successfully with a valid pipeline."""
        from k0.kernel.app import create_app
        from k0.kernel.config import DatabaseSettings, KernelSettings, ServerSettings

        # Create minimal settings
        db_path = tmp_path / "test.db"
        settings = KernelSettings(
            database=DatabaseSettings(path=db_path),
            server=ServerSettings(host="127.0.0.1", port=8000),
        )

        # Create mock pipeline
        mock_pipeline = MagicMock()
        mock_pipeline.on_startup = AsyncMock()
        mock_pipeline.on_shutdown = AsyncMock()

        # Mock discover_and_boot_pipelines to return test pipeline
        with patch("k0.pipelines.loader.discover_and_boot_pipelines") as mock_discover:
            mock_discover.return_value = {"P99_TEST": mock_pipeline}

            # Create app
            app = create_app(settings)

            # Start lifespan
            async with app.router.lifespan_context(app):
                # Verify pipeline was loaded
                assert "P99_TEST" in app.state.pipelines
                assert app.state.pipelines["P99_TEST"] == mock_pipeline

            # After lifespan exits, on_shutdown should have been called
            mock_pipeline.on_shutdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_kernel_graceful_shutdown_calls_pipeline_shutdown(self, tmp_path: Path):
        """Test: Graceful shutdown calls on_shutdown() for all pipelines."""
        from k0.kernel.app import create_app
        from k0.kernel.config import DatabaseSettings, KernelSettings, ServerSettings

        # Create minimal settings
        db_path = tmp_path / "test.db"
        settings = KernelSettings(
            database=DatabaseSettings(path=db_path),
            server=ServerSettings(host="127.0.0.1", port=8000),
        )

        # Create multiple mock pipelines
        pipeline1 = MagicMock()
        pipeline1.on_startup = AsyncMock()
        pipeline1.on_shutdown = AsyncMock()

        pipeline2 = MagicMock()
        pipeline2.on_startup = AsyncMock()
        pipeline2.on_shutdown = AsyncMock()

        # Mock discover_and_boot_pipelines
        with patch("k0.pipelines.loader.discover_and_boot_pipelines") as mock_discover:
            mock_discover.return_value = {
                "P01": pipeline1,
                "P02": pipeline2,
            }

            # Create app
            app = create_app(settings)

            # Start lifespan
            async with app.router.lifespan_context(app):
                # Verify pipelines loaded
                assert len(app.state.pipelines) == 2
                assert "P01" in app.state.pipelines
                assert "P02" in app.state.pipelines

            # After lifespan exits, both on_shutdown should have been called
            pipeline1.on_shutdown.assert_called_once()
            pipeline2.on_shutdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_kernel_records_clean_shutdown_timestamp(self, tmp_path: Path):
        """Test: Clean shutdown timestamp is recorded on graceful exit."""
        from k0.kernel.app import create_app
        from k0.kernel.config import DatabaseSettings, KernelSettings, ServerSettings

        # Create minimal settings
        db_path = tmp_path / "test.db"
        settings = KernelSettings(
            database=DatabaseSettings(path=db_path),
            server=ServerSettings(host="127.0.0.1", port=8000),
        )

        # Mock discover_and_boot_pipelines
        with patch("k0.pipelines.loader.discover_and_boot_pipelines") as mock_discover:
            mock_discover.return_value = {}

            # Create app
            app = create_app(settings)

            # Record time before shutdown
            before_shutdown = int(time.time())

            # Start and stop lifespan
            async with app.router.lifespan_context(app):
                pass  # Just startup and immediate shutdown

            # Verify shutdown timestamp file was created
            shutdown_ts_file = Path("k0_runtime.shutdown_ts")
            assert shutdown_ts_file.exists()

            # Read and verify timestamp
            shutdown_ts = int(shutdown_ts_file.read_text().strip())
            assert shutdown_ts >= before_shutdown
            assert shutdown_ts <= int(time.time())

            # Cleanup
            shutdown_ts_file.unlink()

    @pytest.mark.asyncio
    async def test_kernel_handles_pipeline_on_shutdown_errors(self, tmp_path: Path):
        """Test: Kernel continues shutdown even if pipeline.on_shutdown() fails."""
        from k0.kernel.app import create_app
        from k0.kernel.config import DatabaseSettings, KernelSettings, ServerSettings

        # Create minimal settings
        db_path = tmp_path / "test.db"
        settings = KernelSettings(
            database=DatabaseSettings(path=db_path),
            server=ServerSettings(host="127.0.0.1", port=8000),
        )

        # Create pipeline that raises error on shutdown
        failing_pipeline = MagicMock()
        failing_pipeline.on_startup = AsyncMock()
        failing_pipeline.on_shutdown = AsyncMock(side_effect=RuntimeError("Shutdown error"))

        # Create normal pipeline
        normal_pipeline = MagicMock()
        normal_pipeline.on_startup = AsyncMock()
        normal_pipeline.on_shutdown = AsyncMock()

        # Mock discover_and_boot_pipelines
        with patch("k0.pipelines.loader.discover_and_boot_pipelines") as mock_discover:
            mock_discover.return_value = {
                "P_FAIL": failing_pipeline,
                "P_OK": normal_pipeline,
            }

            # Create app
            app = create_app(settings)

            # Start and stop lifespan (should not raise exception)
            async with app.router.lifespan_context(app):
                pass

            # Both on_shutdown should have been called
            failing_pipeline.on_shutdown.assert_called_once()
            normal_pipeline.on_shutdown.assert_called_once()

            # Verify shutdown timestamp was still recorded despite error
            shutdown_ts_file = Path("k0_runtime.shutdown_ts")
            assert shutdown_ts_file.exists()
            shutdown_ts_file.unlink()

    @pytest.mark.asyncio
    async def test_kernel_handles_pipeline_discovery_errors(self, tmp_path: Path):
        """Test: Kernel continues booting even if pipeline discovery fails."""
        from k0.kernel.app import create_app
        from k0.kernel.config import DatabaseSettings, KernelSettings, ServerSettings

        # Create minimal settings
        db_path = tmp_path / "test.db"
        settings = KernelSettings(
            database=DatabaseSettings(path=db_path),
            server=ServerSettings(host="127.0.0.1", port=8000),
        )

        # Mock discover_and_boot_pipelines to raise error
        with patch("k0.pipelines.loader.discover_and_boot_pipelines") as mock_discover:
            mock_discover.side_effect = RuntimeError("Pipeline discovery failed")

            # Create app (should not raise exception)
            app = create_app(settings)

            # Start lifespan (should handle error gracefully)
            async with app.router.lifespan_context(app):
                # Verify pipelines is empty dict (fallback)
                assert app.state.pipelines == {}

            # Verify app still works despite pipeline discovery failure
            assert app is not None


# ============================================================================
# Acceptance Criteria Summary (M2 R2.3)
# ============================================================================
# ✅ discover_and_boot_pipelines() called in app.py startup
# ✅ Pipelines stored in app.state.pipelines
# ✅ on_shutdown() called for all pipelines on graceful shutdown
# ✅ Clean shutdown timestamp recorded
# ✅ Integration test: test_kernel_boots_with_pipelines() (empty pipelines dir)
# ✅ Integration test: test_kernel_graceful_shutdown_calls_pipeline_shutdown()
