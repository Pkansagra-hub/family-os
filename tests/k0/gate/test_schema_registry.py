"""Unit tests for SchemaRegistry CRUD operations.

Targets k0/gate/schema_registry.py for +33 tests to achieve 100% coverage.
"""

import sqlite3
from unittest import mock

import pytest

from k0.gate.schema_registry import SchemaRecord, SchemaRegistry, _normalize_sha256


class TestSchemaRecord:
    """Test SchemaRecord dataclass."""

    def test_schema_record_creation(self):
        """Test basic SchemaRecord creation."""
        record = SchemaRecord(
            uri="https://example.com/schemas/test",
            version="1.0.0",
            sha256="a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
            status="ACTIVE",
        )
        assert record.uri == "https://example.com/schemas/test"
        assert record.version == "1.0.0"
        assert record.sha256 == "a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3"
        assert record.status == "ACTIVE"
        assert record.operator_id is None
        assert record.blocked_ts is None
        assert record.blocked_reason is None
        assert record.unblocked_ts is None

    def test_schema_record_with_audit_fields(self):
        """Test SchemaRecord with audit trail fields."""
        record = SchemaRecord(
            uri="https://example.com/schemas/test",
            version="1.0.0",
            sha256="a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
            status="BLOCKED",
            operator_id="operator@example.com",
            blocked_ts="2025-01-15T10:00:00Z",
            blocked_reason="Security issue",
            unblocked_ts=None,
        )
        assert record.operator_id == "operator@example.com"
        assert record.blocked_ts == "2025-01-15T10:00:00Z"
        assert record.blocked_reason == "Security issue"
        assert record.unblocked_ts is None


class TestNormalizeSha256:
    """Test SHA256 normalization utility."""

    def test_normalize_sha256_valid(self):
        """Test normalization of valid SHA256."""
        result = _normalize_sha256(
            "A665A45920422F9D417E4867EFDC4FB8A04A1F3FFF1FA07E998E86F7F7A27AE3"
        )
        assert result == "a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3"

    def test_normalize_sha256_valid_lowercase(self):
        """Test normalization of already lowercase SHA256."""
        sha256 = "a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3"
        result = _normalize_sha256(sha256)
        assert result == sha256

    def test_normalize_sha256_with_whitespace(self):
        """Test normalization strips whitespace."""
        result = _normalize_sha256(
            " a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3 "
        )
        assert result == "a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3"

    def test_normalize_sha256_invalid_length_short(self):
        """Test rejection of too-short SHA256."""
        with pytest.raises(ValueError, match="sha256 must be a 64-character"):
            _normalize_sha256("a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae")

    def test_normalize_sha256_invalid_length_long(self):
        """Test rejection of too-long SHA256."""
        with pytest.raises(ValueError, match="sha256 must be a 64-character"):
            _normalize_sha256("a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3a")

    def test_normalize_sha256_invalid_characters(self):
        """Test rejection of non-hexadecimal characters."""
        with pytest.raises(ValueError, match="sha256 must be a hexadecimal digest"):
            _normalize_sha256("g665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3")


class TestSchemaRegistryInitialization:
    """Test SchemaRegistry initialization and basic operations."""

    def test_schema_registry_init(self):
        """Test SchemaRegistry initialization."""
        registry = SchemaRegistry()
        assert registry._cache == {}
        assert registry._loaded is False
        assert registry._metrics_exporter is None

    def test_schema_registry_init_with_metrics(self):
        """Test SchemaRegistry initialization with metrics exporter."""
        metrics = mock.Mock()
        registry = SchemaRegistry(metrics_exporter=metrics)
        assert registry._metrics_exporter is metrics

    def test_clear_cache(self):
        """Test cache clearing."""
        metrics = mock.Mock()
        registry = SchemaRegistry(metrics_exporter=metrics)

        # Populate cache
        registry._cache = {("test", "1.0"): mock.Mock()}
        registry._loaded = True

        registry.clear_cache()

        assert registry._cache == {}
        assert registry._loaded is False
        metrics.set_gauge.assert_called_once_with("schema_cache_entries_active", 0.0)


class TestSchemaRegistryLoad:
    """Test schema loading functionality."""

    def test_load_empty_registry(self, in_memory_db):
        """Test loading from empty schema registry."""
        registry = SchemaRegistry()

        registry.load(connection=in_memory_db)

        assert registry._loaded is True
        assert registry._cache == {}

    def test_load_with_schemas(self, in_memory_db):
        """Test loading schemas into cache."""
        # Setup test data
        in_memory_db.execute(
            """
            INSERT INTO schema_registry (schema_uri, version, sha256, status, operator_id)
            VALUES (?, ?, ?, ?, ?)
        """,
            (
                "https://example.com/schemas/test",
                "1.0.0",
                "a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
                "ACTIVE",
                "operator@example.com",
            ),
        )

        registry = SchemaRegistry()
        registry.load(connection=in_memory_db)

        assert registry._loaded is True
        assert len(registry._cache) == 1

        key = ("https://example.com/schemas/test", "1.0.0")
        assert key in registry._cache

        record = registry._cache[key]
        assert record.uri == "https://example.com/schemas/test"
        assert record.version == "1.0.0"
        assert record.status == "ACTIVE"
        assert record.operator_id == "operator@example.com"

    def test_load_with_metrics(self, in_memory_db):
        """Test loading with metrics emission."""
        # Setup test data
        in_memory_db.execute(
            """
            INSERT INTO schema_registry (schema_uri, version, sha256, status)
            VALUES (?, ?, ?, ?)
        """,
            (
                "https://example.com/schemas/test",
                "1.0.0",
                "a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
                "ACTIVE",
            ),
        )

        metrics = mock.Mock()
        registry = SchemaRegistry(metrics_exporter=metrics)

        registry.load(connection=in_memory_db)

        metrics.set_gauge.assert_called_once_with("schema_cache_entries_active", 1.0)


class TestSchemaRegistryGet:
    """Test schema retrieval functionality."""

    def test_get_cache_hit(self):
        """Test retrieving schema from cache."""
        metrics = mock.Mock()
        registry = SchemaRegistry(metrics_exporter=metrics)

        record = SchemaRecord(
            uri="https://example.com/schemas/test",
            version="1.0.0",
            sha256="a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
            status="ACTIVE",
        )

        registry._cache[("https://example.com/schemas/test", "1.0.0")] = record

        result = registry.get("https://example.com/schemas/test", "1.0.0")

        assert result == record
        metrics.emit.assert_called_once_with("schema_cache_hits_total")

    def test_get_cache_miss_found_in_db(self, in_memory_db):
        """Test retrieving schema from database when not in cache."""
        # Setup test data
        in_memory_db.execute(
            """
            INSERT INTO schema_registry (schema_uri, version, sha256, status, operator_id, blocked_ts)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (
                "https://example.com/schemas/test",
                "1.0.0",
                "a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
                "ACTIVE",
                "operator@example.com",
                "2025-01-15T10:00:00Z",
            ),
        )

        metrics = mock.Mock()
        registry = SchemaRegistry(metrics_exporter=metrics)

        result = registry.get("https://example.com/schemas/test", "1.0.0", connection=in_memory_db)

        assert result.uri == "https://example.com/schemas/test"
        assert result.version == "1.0.0"
        assert result.status == "ACTIVE"
        assert result.operator_id == "operator@example.com"
        assert result.blocked_ts == "2025-01-15T10:00:00Z"

        # Should be cached now
        assert ("https://example.com/schemas/test", "1.0.0") in registry._cache

        # Check metrics
        metrics.emit.assert_called_once_with("schema_cache_misses_total")
        metrics.set_gauge.assert_called_once_with("schema_cache_entries_active", 1.0)

    def test_get_not_found(self, in_memory_db):
        """Test retrieving non-existent schema."""
        registry = SchemaRegistry()

        with pytest.raises(
            KeyError, match="Schema https://example.com/schemas/test@1.0.0 not found"
        ):
            registry.get("https://example.com/schemas/test", "1.0.0", connection=in_memory_db)


class TestSchemaRegistryRegister:
    """Test schema registration functionality."""

    def test_register_success(self, in_memory_db):
        """Test successful schema registration."""
        registry = SchemaRegistry()

        record = SchemaRecord(
            uri="https://example.com/schemas/test",
            version="1.0.0",
            sha256="a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
            status="REGISTERED",
        )

        result = registry.register(record, connection=in_memory_db)

        assert result.uri == "https://example.com/schemas/test"
        assert result.version == "1.0.0"
        assert result.status == "REGISTERED"

        # Check database
        row = in_memory_db.execute(
            """
            SELECT schema_uri, version, sha256, status FROM schema_registry
            WHERE schema_uri=? AND version=?
        """,
            ("https://example.com/schemas/test", "1.0.0"),
        ).fetchone()

        assert row["schema_uri"] == "https://example.com/schemas/test"
        assert row["version"] == "1.0.0"
        assert row["status"] == "REGISTERED"

        # Check cache
        assert ("https://example.com/schemas/test", "1.0.0") in registry._cache

    def test_register_duplicate(self, in_memory_db):
        """Test registration of already existing schema."""
        # Setup table with existing record
        in_memory_db.execute(
            """
            INSERT INTO schema_registry (schema_uri, version, sha256, status)
            VALUES (?, ?, ?, ?)
        """,
            (
                "https://example.com/schemas/test",
                "1.0.0",
                "a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
                "REGISTERED",
            ),
        )

        registry = SchemaRegistry()

        record = SchemaRecord(
            uri="https://example.com/schemas/test",
            version="1.0.0",
            sha256="a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
            status="REGISTERED",
        )

        with pytest.raises(
            ValueError, match="Schema https://example.com/schemas/test@1.0.0 already exists"
        ):
            registry.register(record, connection=in_memory_db)

    def test_register_invalid_record(self, in_memory_db):
        """Test registration with invalid record data."""
        registry = SchemaRegistry()

        # Empty URI
        record = SchemaRecord(
            uri="",
            version="1.0.0",
            sha256="a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
            status="REGISTERED",
        )

        with pytest.raises(ValueError, match="schema_uri must not be empty"):
            registry.register(record, connection=in_memory_db)


class TestSchemaRegistryUpsert:
    """Test schema upsert functionality."""

    def test_upsert_insert(self, in_memory_db):
        """Test upsert creating new record."""
        registry = SchemaRegistry()

        record = SchemaRecord(
            uri="https://example.com/schemas/test",
            version="1.0.0",
            sha256="a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
            status="REGISTERED",
        )

        result = registry.upsert(record, connection=in_memory_db)

        assert result.uri == "https://example.com/schemas/test"
        assert result.version == "1.0.0"
        assert result.status == "REGISTERED"

        # Check database
        row = in_memory_db.execute(
            """
            SELECT schema_uri, version, sha256, status FROM schema_registry
            WHERE schema_uri=? AND version=?
        """,
            ("https://example.com/schemas/test", "1.0.0"),
        ).fetchone()

        assert row["status"] == "REGISTERED"

    def test_upsert_update(self, in_memory_db):
        """Test upsert updating existing record."""
        # Insert existing record
        in_memory_db.execute(
            """
            INSERT INTO schema_registry (schema_uri, version, sha256, status)
            VALUES (?, ?, ?, ?)
        """,
            (
                "https://example.com/schemas/test",
                "1.0.0",
                "a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
                "REGISTERED",
            ),
        )

        registry = SchemaRegistry()

        # Upsert with updated status
        record = SchemaRecord(
            uri="https://example.com/schemas/test",
            version="1.0.0",
            sha256="b665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
            status="ACTIVE",
        )

        result = registry.upsert(record, connection=in_memory_db)

        assert result.status == "ACTIVE"

        # Check database was updated
        row = in_memory_db.execute(
            """
            SELECT schema_uri, version, sha256, status FROM schema_registry
            WHERE schema_uri=? AND version=?
        """,
            ("https://example.com/schemas/test", "1.0.0"),
        ).fetchone()

        assert row["status"] == "ACTIVE"
        assert row["sha256"] == "b665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3"


class TestSchemaRegistryPromote:
    """Test schema promotion functionality."""

    def test_promote_to_active(self, in_memory_db):
        """Test promoting a schema to ACTIVE status."""
        # Insert test data - REGISTERED schema to promote
        in_memory_db.execute(
            """
            INSERT INTO schema_registry (schema_uri, version, sha256, status)
            VALUES (?, ?, ?, ?)
        """,
            (
                "https://example.com/schemas/test",
                "1.0.0",
                "a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
                "REGISTERED",
            ),
        )

        registry = SchemaRegistry()
        result = registry.promote(
            "https://example.com/schemas/test", "1.0.0", connection=in_memory_db
        )

        assert result.status == "ACTIVE"

        # Check database
        row = in_memory_db.execute(
            """
            SELECT status FROM schema_registry
            WHERE schema_uri=? AND version=?
        """,
            ("https://example.com/schemas/test", "1.0.0"),
        ).fetchone()

        assert row["status"] == "ACTIVE"

    def test_promote_with_demotion(self, in_memory_db):
        """Test promoting schema demotes other versions."""
        # Insert multiple versions
        versions = [
            ("1.0.0", "REGISTERED"),
            ("1.1.0", "ACTIVE"),
            ("2.0.0", "DEPRECATED"),
        ]

        for version, status in versions:
            in_memory_db.execute(
                """
                INSERT INTO schema_registry (schema_uri, version, sha256, status)
                VALUES (?, ?, ?, ?)
            """,
                (
                    "https://example.com/schemas/test",
                    version,
                    "a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
                    status,
                ),
            )

        registry = SchemaRegistry()
        result = registry.promote(
            "https://example.com/schemas/test", "1.0.0", connection=in_memory_db
        )

        assert result.status == "ACTIVE"

        # Check all versions have correct status
        rows = in_memory_db.execute(
            """
            SELECT version, status FROM schema_registry
            WHERE schema_uri=?
            ORDER BY version
        """,
            ("https://example.com/schemas/test",),
        ).fetchall()

        expected = [
            ("1.0.0", "ACTIVE"),
            ("1.1.0", "DEPRECATED"),
            ("2.0.0", "BLOCKED"),
        ]

        for row, (version, status) in zip(rows, expected):
            assert row["version"] == version
            assert row["status"] == status

    def test_promote_blocked_schema(self, in_memory_db):
        """Test promoting a previously blocked schema."""
        # Insert blocked schema with operator_id
        in_memory_db.execute(
            """
            INSERT INTO schema_registry (schema_uri, version, sha256, status, operator_id, blocked_ts, blocked_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (
                "https://example.com/schemas/test",
                "1.0.0",
                "a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
                "BLOCKED",
                "operator@example.com",
                "2025-01-15T10:00:00Z",
                "Security issue",
            ),
        )

        registry = SchemaRegistry()
        result = registry.promote(
            "https://example.com/schemas/test", "1.0.0", connection=in_memory_db
        )

        assert result.status == "ACTIVE"
        assert result.unblocked_ts is not None  # Should be set

    def test_promote_not_found(self, in_memory_db):
        """Test promoting non-existent schema."""
        registry = SchemaRegistry()

        with pytest.raises(
            KeyError, match="Schema https://example.com/schemas/test@1.0.0 not found"
        ):
            registry.promote("https://example.com/schemas/test", "1.0.0", connection=in_memory_db)


class TestSchemaRegistryBlock:
    """Test schema blocking functionality."""

    def test_block_success(self, in_memory_db):
        """Test successful schema blocking."""
        # Insert active schema
        in_memory_db.execute(
            """
            INSERT INTO schema_registry (schema_uri, version, sha256, status)
            VALUES (?, ?, ?, ?)
        """,
            (
                "https://example.com/schemas/test",
                "1.0.0",
                "a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
                "ACTIVE",
            ),
        )

        registry = SchemaRegistry()

        result = registry.block(
            "https://example.com/schemas/test",
            "1.0.0",
            operator_id="operator@example.com",
            reason="Security vulnerability",
            connection=in_memory_db,
        )

        assert result.status == "BLOCKED"
        assert result.operator_id == "operator@example.com"
        assert result.blocked_reason == "Security vulnerability"
        assert result.blocked_ts is not None
        assert result.unblocked_ts is None

    def test_block_empty_operator_id(self, in_memory_db):
        """Test blocking with empty operator_id."""
        registry = SchemaRegistry()

        with pytest.raises(ValueError, match="operator_id is required for block operations"):
            registry.block(
                "https://example.com/schemas/test",
                "1.0.0",
                operator_id="",
                reason="Security issue",
                connection=in_memory_db,
            )

    def test_block_empty_reason(self, in_memory_db):
        """Test blocking with empty reason."""
        registry = SchemaRegistry()

        with pytest.raises(ValueError, match="reason is required for block operations"):
            registry.block(
                "https://example.com/schemas/test",
                "1.0.0",
                operator_id="operator@example.com",
                reason="",
                connection=in_memory_db,
            )

    def test_block_not_found(self, in_memory_db):
        """Test blocking non-existent schema."""
        registry = SchemaRegistry()

        with pytest.raises(
            KeyError, match="Schema https://example.com/schemas/test@1.0.0 not found"
        ):
            registry.block(
                "https://example.com/schemas/test",
                "1.0.0",
                operator_id="operator@example.com",
                reason="Security issue",
                connection=in_memory_db,
            )


class TestSchemaRegistryQueries:
    """Test schema query functionality."""

    def test_active_versions(self):
        """Test retrieving active versions for a URI."""
        registry = SchemaRegistry()

        # Setup cache with mixed statuses
        records = [
            SchemaRecord("https://example.com/schemas/test", "1.0.0", "sha1", "ACTIVE"),
            SchemaRecord("https://example.com/schemas/test", "1.1.0", "sha2", "DEPRECATED"),
            SchemaRecord("https://example.com/schemas/test", "2.0.0", "sha3", "BLOCKED"),
            SchemaRecord("https://example.com/schemas/other", "1.0.0", "sha4", "ACTIVE"),
        ]

        for record in records:
            registry._cache[(record.uri, record.version)] = record

        active_versions = list(registry.active_versions("https://example.com/schemas/test"))

        assert len(active_versions) == 1
        assert active_versions[0].version == "1.0.0"
        assert active_versions[0].status == "ACTIVE"

    def test_records_for_uri(self):
        """Test retrieving all records for a URI."""
        registry = SchemaRegistry()

        # Setup cache
        records = [
            SchemaRecord("https://example.com/schemas/test", "1.0.0", "sha1", "ACTIVE"),
            SchemaRecord("https://example.com/schemas/test", "1.1.0", "sha2", "DEPRECATED"),
            SchemaRecord("https://example.com/schemas/other", "1.0.0", "sha3", "ACTIVE"),
        ]

        for record in records:
            registry._cache[(record.uri, record.version)] = record

        uri_records = list(registry.records_for_uri("https://example.com/schemas/test"))

        assert len(uri_records) == 2
        versions = {r.version for r in uri_records}
        assert versions == {"1.0.0", "1.1.0"}

    def test_get_audit_trail_all(self, in_memory_db):
        """Test retrieving complete audit trail."""
        # Insert test data
        audit_data = [
            (
                "https://example.com/schemas/test",
                "1.0.0",
                "ACTIVE",
                "op1@example.com",
                None,
                None,
                None,
            ),
            (
                "https://example.com/schemas/test",
                "1.1.0",
                "BLOCKED",
                "op2@example.com",
                "2025-01-15T10:00:00Z",
                "Security",
                None,
            ),
        ]

        for (
            uri,
            version,
            status,
            operator_id,
            blocked_ts,
            blocked_reason,
            unblocked_ts,
        ) in audit_data:
            in_memory_db.execute(
                """
                INSERT INTO schema_registry (schema_uri, version, sha256, status, operator_id, blocked_ts, blocked_reason, unblocked_ts)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    uri,
                    version,
                    "a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
                    status,
                    operator_id,
                    blocked_ts,
                    blocked_reason,
                    unblocked_ts,
                ),
            )

        registry = SchemaRegistry()
        audit_trail = list(registry.get_audit_trail(connection=in_memory_db))

        assert len(audit_trail) == 2

    def test_get_audit_trail_filtered_by_uri(self, in_memory_db):
        """Test audit trail filtered by URI."""
        # Insert test data for different URIs
        uris = ["https://example.com/schemas/test", "https://example.com/schemas/other"]
        for uri in uris:
            in_memory_db.execute(
                """
                INSERT INTO schema_registry (schema_uri, version, sha256, status)
                VALUES (?, ?, ?, ?)
            """,
                (
                    uri,
                    "1.0.0",
                    "a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
                    "ACTIVE",
                ),
            )

        registry = SchemaRegistry()
        audit_trail = list(
            registry.get_audit_trail(
                uri="https://example.com/schemas/test", connection=in_memory_db
            )
        )

        assert len(audit_trail) == 1
        assert audit_trail[0].uri == "https://example.com/schemas/test"

    def test_get_audit_trail_filtered_by_status(self, in_memory_db):
        """Test audit trail filtered by status."""
        # Insert test data with different statuses
        statuses = ["ACTIVE", "BLOCKED", "DEPRECATED"]
        for i, status in enumerate(statuses):
            in_memory_db.execute(
                """
                INSERT INTO schema_registry (schema_uri, version, sha256, status)
                VALUES (?, ?, ?, ?)
            """,
                (
                    "https://example.com/schemas/test",
                    f"1.{i}.0",
                    "a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
                    status,
                ),
            )

        registry = SchemaRegistry()
        audit_trail = list(registry.get_audit_trail(status="BLOCKED", connection=in_memory_db))

        assert len(audit_trail) == 1
        assert audit_trail[0].status == "BLOCKED"

    def test_get_audit_trail_version_requires_uri(self, in_memory_db):
        """Test that version filter requires URI."""
        registry = SchemaRegistry()

        with pytest.raises(ValueError, match="version filter requires uri parameter"):
            list(registry.get_audit_trail(version="1.0.0", connection=in_memory_db))


class TestSchemaRegistryInternalMethods:
    """Test internal SchemaRegistry methods."""

    def test_normalize_record_success(self):
        """Test successful record normalization."""
        registry = SchemaRegistry()

        record = SchemaRecord(
            uri="  https://example.com/schemas/test  ",
            version="  1.0.0  ",
            sha256="A665A45920422F9D417E4867EFDC4FB8A04A1F3FFF1FA07E998E86F7F7A27AE3",
            status=" active ",
        )

        normalized = registry._normalize_record(record)

        assert normalized.uri == "https://example.com/schemas/test"
        assert normalized.version == "1.0.0"
        assert (
            normalized.sha256 == "a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3"
        )
        assert normalized.status == "ACTIVE"

    def test_normalize_record_empty_uri(self):
        """Test normalization with empty URI."""
        registry = SchemaRegistry()

        record = SchemaRecord(
            uri="",
            version="1.0.0",
            sha256="a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
            status="ACTIVE",
        )

        with pytest.raises(ValueError, match="schema_uri must not be empty"):
            registry._normalize_record(record)

    def test_normalize_record_empty_version(self):
        """Test normalization with empty version."""
        registry = SchemaRegistry()

        record = SchemaRecord(
            uri="https://example.com/schemas/test",
            version="",
            sha256="a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
            status="ACTIVE",
        )

        with pytest.raises(ValueError, match="version must not be empty"):
            registry._normalize_record(record)

    def test_normalize_record_invalid_status(self):
        """Test normalization with invalid status."""
        registry = SchemaRegistry()

        record = SchemaRecord(
            uri="https://example.com/schemas/test",
            version="1.0.0",
            sha256="a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
            status="INVALID",
        )

        with pytest.raises(ValueError, match="status must be one of"):
            registry._normalize_record(record)

    def test_store_record(self):
        """Test storing record in cache."""
        registry = SchemaRegistry()

        record = SchemaRecord(
            uri="https://example.com/schemas/test",
            version="1.0.0",
            sha256="a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
            status="ACTIVE",
        )

        registry._store(record)

        assert registry._loaded is True
        assert ("https://example.com/schemas/test", "1.0.0") in registry._cache
        assert registry._cache[("https://example.com/schemas/test", "1.0.0")] == record

    def test_refresh_uri_cache(self):
        """Test refreshing cache for a specific URI."""
        registry = SchemaRegistry()

        # Setup initial cache
        old_record = SchemaRecord("https://example.com/schemas/test", "1.0.0", "old_sha", "ACTIVE")
        registry._cache[("https://example.com/schemas/test", "1.0.0")] = old_record

        # Mock rows from database
        mock_row1 = mock.Mock()
        mock_row1.__getitem__ = mock.Mock(
            side_effect=lambda key: {
                "schema_uri": "https://example.com/schemas/test",
                "version": "1.0.0",
                "sha256": "new_sha",
                "status": "BLOCKED",
                "operator_id": "operator@example.com",
                "blocked_ts": "2025-01-15T10:00:00Z",
                "blocked_reason": "Updated",
                "unblocked_ts": None,
            }[key]
        )

        mock_row2 = mock.Mock()
        mock_row2.__getitem__ = mock.Mock(
            side_effect=lambda key: {
                "schema_uri": "https://example.com/schemas/test",
                "version": "1.1.0",
                "sha256": "sha2",
                "status": "ACTIVE",
                "operator_id": None,
                "blocked_ts": None,
                "blocked_reason": None,
                "unblocked_ts": None,
            }[key]
        )

        mock_rows = [mock_row1, mock_row2]

        registry._refresh_uri_cache("https://example.com/schemas/test", mock_rows)  # type: ignore

        # Check cache was updated
        assert len(registry._cache) == 2
        assert ("https://example.com/schemas/test", "1.0.0") in registry._cache
        assert ("https://example.com/schemas/test", "1.1.0") in registry._cache

        updated_record = registry._cache[("https://example.com/schemas/test", "1.0.0")]
        assert updated_record.sha256 == "new_sha"
        assert updated_record.status == "BLOCKED"
        assert updated_record.operator_id == "operator@example.com"


@pytest.fixture
def in_memory_db():
    """In-memory SQLite database with schema_registry table created."""
    conn = sqlite3.connect(":memory:")

    # Create the schema_registry table
    conn.execute(
        """
        CREATE TABLE schema_registry (
            schema_uri TEXT,
            version TEXT,
            sha256 TEXT,
            status TEXT,
            operator_id TEXT,
            blocked_ts TEXT,
            blocked_reason TEXT,
            unblocked_ts TEXT,
            PRIMARY KEY (schema_uri, version)
        )
    """
    )

    yield conn
    conn.close()
