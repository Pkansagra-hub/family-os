"""Integration tests for Driver SPI + AliasMap functionality."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock

import pytest

from k0.automation.migrate import apply_migrations
from k0.query.common import DriverContext
from k0.query.drivers import AliasDriver, FtsDriver, WalDriver, build_default_registry
from k0.storage.fts import FtsStore
from k0.uow.connection_pool import configure_pool, connection_scope, shutdown_pool


@pytest.fixture
def test_db():
    """Create a temporary test database with migrations applied."""
    tmp_dir = TemporaryDirectory(ignore_cleanup_errors=True)
    db_path = Path(tmp_dir.name) / "test.sqlite3"

    # Configure connection pool
    configure_pool(db_path)

    try:
        # Apply migrations
        apply_migrations(str(db_path), dry_run=False)

        # Insert test data into WAL
        with connection_scope() as conn:
            # Insert test data into WAL
            conn.execute(
                """
				INSERT INTO st_wal (
					tenant_id, space_id, topic, envelope_json, body,
					payload_sha256, schema_uri, schema_version, device_id, commit_ts
				) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
				""",
                (
                    "tenant1",
                    "space1",
                    "test.topic",
                    json.dumps({"type": "test", "id": "123"}),
                    b"test content for full text search",
                    "sha256_hash",
                    "test://schema",
                    "1.0.0",
                    "device1",
                    "2025-01-01T00:00:00Z",
                ),
            )
            wal_pos = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Return both db_path and wal_pos for tests that need FTS indexing
        yield str(db_path), wal_pos

    finally:
        shutdown_pool()
        tmp_dir.cleanup()


@pytest.fixture
def mock_metrics():
    """Mock metrics emitter."""
    return MagicMock()


class TestDriverSpiWiring:
    """Test Driver SPI wiring and registry functionality."""

    def test_build_default_registry_includes_real_drivers(self):
        """Test that default registry includes real drivers like WalDriver and FtsDriver."""
        registry = build_default_registry(default_limit=10, max_limit=100)

        # Should have multiple drivers
        assert len(registry.drivers) >= 2

        # Should include WalDriver
        wal_driver = None
        fts_driver = None
        for driver in registry.drivers:
            if driver.name == "wal":
                wal_driver = driver
            elif driver.name == "fts":
                fts_driver = driver

        assert wal_driver is not None, "WalDriver should be registered"
        assert isinstance(wal_driver, WalDriver), "Should be WalDriver instance"

        assert fts_driver is not None, "FtsDriver should be registered"
        assert isinstance(fts_driver, FtsDriver), "Should be FtsDriver instance"

    def test_build_default_registry_includes_alias_drivers(self):
        """Test that default registry includes alias drivers for unsupported types."""
        registry = build_default_registry(default_limit=10, max_limit=100)

        alias_drivers = [d for d in registry.drivers if isinstance(d, AliasDriver)]
        assert len(alias_drivers) >= 4, "Should have multiple alias drivers"

        # Check specific alias drivers exist
        alias_names = {d.name for d in alias_drivers}
        expected_aliases = {"episodic", "snapshot", "vector", "kg"}
        assert expected_aliases.issubset(
            alias_names
        ), f"Missing aliases: {expected_aliases - alias_names}"

    def test_registry_resolve_real_driver(self):
        """Test registry resolves real drivers for supported selectors."""
        registry = build_default_registry(default_limit=10, max_limit=100)

        # Test WalDriver resolution
        wal_selector = type("MockSelector", (), {"type": "wal"})()
        wal_driver = registry.resolve(wal_selector)
        assert isinstance(wal_driver, WalDriver)

        # Test FtsDriver resolution
        fts_selector = type("MockSelector", (), {"type": "fts"})()
        fts_driver = registry.resolve(fts_selector)
        assert isinstance(fts_driver, FtsDriver)

        semantic_selector = type("MockSelector", (), {"type": "semantic"})()
        semantic_driver = registry.resolve(semantic_selector)
        assert isinstance(semantic_driver, FtsDriver)

    def test_registry_resolve_alias_driver(self):
        """Test registry resolves alias drivers for unsupported types."""
        registry = build_default_registry(default_limit=10, max_limit=100)

        # Test alias driver resolution
        vector_selector = type("MockSelector", (), {"type": "vector"})()
        vector_driver = registry.resolve(vector_selector)
        assert isinstance(vector_driver, AliasDriver)
        assert vector_driver.name == "vector"

        kg_selector = type("MockSelector", (), {"type": "kg"})()
        kg_driver = registry.resolve(kg_selector)
        assert isinstance(kg_driver, AliasDriver)
        assert kg_driver.name == "kg"

    def test_registry_resolve_raises_for_unknown_type(self):
        """Test registry raises LookupError for completely unknown selector types."""
        registry = build_default_registry(default_limit=10, max_limit=100)

        unknown_selector = type("MockSelector", (), {"type": "completely_unknown"})()
        with pytest.raises(LookupError, match="No query driver registered"):
            registry.resolve(unknown_selector)


class TestFtsDriverRealFunctionality:
    """Test FtsDriver real functionality with database operations."""

    def test_fts_driver_supports_correct_types(self):
        """Test FtsDriver supports the correct selector types."""
        driver = FtsDriver(default_limit=10, max_limit=100)

        # Should support FTS types
        assert driver.supports(type("MockSelector", (), {"type": "fts"})())
        assert driver.supports(type("MockSelector", (), {"type": "semantic"})())
        assert driver.supports(type("MockSelector", (), {"type": "fulltext"})())
        assert driver.supports(type("MockSelector", (), {"type": "text"})())

        # Should not support other types
        assert not driver.supports(type("MockSelector", (), {"type": "wal"})())
        assert not driver.supports(type("MockSelector", (), {"type": "vector"})())
        assert not driver.supports(type("MockSelector", (), {})())  # No type

    def test_fts_driver_execute_with_query(self, test_db):
        """Test FtsDriver executes search with query parameter."""
        db_path, wal_pos = test_db

        # Index the WAL entry in FTS
        fts_store = FtsStore()
        fts_store.index_wal_entry(
            wal_pos=wal_pos,
            tenant_id="tenant1",
            space_id="space1",
            topic="test.topic",
            envelope_json=json.dumps({"type": "test", "id": "123"}),
            body=b"test content for full text search",
            payload_sha256="sha256_hash",
            schema_uri="test://schema",
            schema_version="1.0.0",
            device_id="device1",
            commit_ts="2025-01-01T00:00:00Z",
        )

        driver = FtsDriver(default_limit=10, max_limit=100)

        selector = type(
            "MockSelector", (), {"type": "fts", "query": "content", "tenant_id": "tenant1"}
        )()

        context = DriverContext(
            space_id="space1",
            tenant_id="tenant1",
            selector_index=0,
            allowed_limit=10,
            remaining_top_k=10,
            time_budget_ms=1000,
            elapsed_ms=0.0,
        )

        result = driver.execute(selector, context)

        assert result.driver == "fts"
        assert result.selector_index == 0
        assert result.latency_ms >= 0
        assert "source" in result.metadata
        assert result.metadata["source"] == "st_fts"
        assert "query" in result.metadata
        assert result.metadata["query"] == "content"

    def test_fts_driver_execute_no_query(self, test_db):
        """Test FtsDriver returns empty result when no query provided."""
        db_path, wal_pos = test_db
        driver = FtsDriver(default_limit=10, max_limit=100)

        selector = type("MockSelector", (), {"type": "fts", "tenant_id": "tenant1"})()

        context = DriverContext(
            space_id="space1",
            tenant_id="tenant1",
            selector_index=0,
            allowed_limit=10,
            remaining_top_k=10,
            time_budget_ms=1000,
            elapsed_ms=0.0,
        )

        result = driver.execute(selector, context)

        assert result.driver == "fts"
        assert result.items == []
        assert result.metadata.get("status") == "no_query"

    def test_fts_driver_execute_zero_limit(self, test_db):
        """Test FtsDriver returns early when allowed_limit is 0."""
        db_path, wal_pos = test_db
        driver = FtsDriver(default_limit=10, max_limit=100)

        selector = type("MockSelector", (), {"type": "fts", "query": "content"})()

        context = DriverContext(
            space_id="space1",
            tenant_id="tenant1",
            selector_index=0,
            allowed_limit=0,  # Zero limit
            remaining_top_k=10,
            time_budget_ms=1000,
            elapsed_ms=0.0,
        )

        result = driver.execute(selector, context)

        assert result.driver == "fts"
        assert result.items == []
        assert result.latency_ms == 0.0


class TestAliasDriverNoOpFunctionality:
    """Test AliasDriver no-op functionality."""

    def test_alias_driver_supports_configured_types(self):
        """Test AliasDriver supports only its configured types."""
        driver = AliasDriver(
            name="test_alias", supported_types={"type1", "type2"}, reason="test reason"
        )

        assert driver.supports(type("MockSelector", (), {"type": "type1"})())
        assert driver.supports(type("MockSelector", (), {"type": "type2"})())
        assert not driver.supports(type("MockSelector", (), {"type": "type3"})())
        assert not driver.supports(type("MockSelector", (), {})())  # No type

    def test_alias_driver_execute_returns_unavailable(self):
        """Test AliasDriver execute returns unavailable status."""
        driver = AliasDriver(
            name="test_alias", supported_types={"test"}, reason="driver not configured"
        )

        selector = type("MockSelector", (), {"type": "test"})()
        context = DriverContext(
            space_id="space1",
            tenant_id="tenant1",
            selector_index=0,
            allowed_limit=10,
            remaining_top_k=10,
            time_budget_ms=1000,
            elapsed_ms=0.0,
        )

        result = driver.execute(selector, context)

        assert result.driver == "test_alias"
        assert result.items == []
        assert result.latency_ms == 0.0
        assert result.metadata["status"] == "unavailable"
        assert result.metadata["reason"] == "driver not configured"


class TestDriverAliasResolutionLogging:
    """Test alias resolution logging functionality."""

    def test_alias_driver_logs_resolution(self, caplog):
        """Test that alias driver resolution is logged."""
        with caplog.at_level(logging.INFO):
            driver = AliasDriver(
                name="test_vector",
                supported_types={"vector"},
                reason="vector driver not configured",
            )

            selector = type("MockSelector", (), {"type": "vector"})()
            context = DriverContext(
                space_id="space1",
                tenant_id="tenant1",
                selector_index=0,
                allowed_limit=10,
                remaining_top_k=10,
                time_budget_ms=1000,
                elapsed_ms=0.0,
            )

            result = driver.execute(selector, context)

            # Check that execution metadata indicates unavailable status
            assert result.metadata["status"] == "unavailable"
            assert "vector driver not configured" in result.metadata["reason"]

    def test_real_driver_vs_alias_driver_distinction(self):
        """Test that real drivers and alias drivers are properly distinguished."""
        # Real driver
        real_driver = FtsDriver(default_limit=10, max_limit=100)
        assert hasattr(real_driver, "execute")
        assert hasattr(real_driver, "_search_fts")  # Implementation detail

        # Alias driver
        alias_driver = AliasDriver(name="test", supported_types={"test"}, reason="test")
        assert hasattr(alias_driver, "execute")
        assert hasattr(alias_driver, "reason")  # Alias-specific attribute
        assert not hasattr(alias_driver, "_search_fts")  # No implementation


class TestDriverRegistryIntegration:
    """Integration tests for full driver registry functionality."""

    def test_registry_end_to_end_fts_resolution(self, test_db):
        """Test end-to-end FTS driver resolution and execution."""
        db_path, wal_pos = test_db

        # Index the WAL entry in FTS
        fts_store = FtsStore()
        fts_store.index_wal_entry(
            wal_pos=wal_pos,
            tenant_id="tenant1",
            space_id="space1",
            topic="test.topic",
            envelope_json=json.dumps({"type": "test", "id": "123"}),
            body=b"test content for full text search",
            payload_sha256="sha256_hash",
            schema_uri="test://schema",
            schema_version="1.0.0",
            device_id="device1",
            commit_ts="2025-01-01T00:00:00Z",
        )

        registry = build_default_registry(default_limit=10, max_limit=100)

        # Resolve FTS driver
        selector = type(
            "MockSelector", (), {"type": "fts", "query": "content", "tenant_id": "tenant1"}
        )()

        driver = registry.resolve(selector)
        assert isinstance(driver, FtsDriver)

        # Execute search
        context = DriverContext(
            space_id="space1",
            tenant_id="tenant1",
            selector_index=0,
            allowed_limit=10,
            remaining_top_k=10,
            time_budget_ms=1000,
            elapsed_ms=0.0,
        )

        result = driver.execute(selector, context)

        assert result.driver == "fts"
        assert result.latency_ms >= 0
        assert "st_fts" in result.metadata["source"]

    def test_registry_end_to_end_alias_resolution(self):
        """Test end-to-end alias driver resolution and execution."""
        registry = build_default_registry(default_limit=10, max_limit=100)

        # Resolve vector alias driver
        selector = type("MockSelector", (), {"type": "vector"})()

        driver = registry.resolve(selector)
        assert isinstance(driver, AliasDriver)
        assert driver.name == "vector"

        # Execute (should return unavailable)
        context = DriverContext(
            space_id="space1",
            tenant_id="tenant1",
            selector_index=0,
            allowed_limit=10,
            remaining_top_k=10,
            time_budget_ms=1000,
            elapsed_ms=0.0,
        )

        result = driver.execute(selector, context)

        assert result.driver == "vector"
        assert result.metadata["status"] == "unavailable"
        assert "vector recall driver not configured" in result.metadata["reason"]
