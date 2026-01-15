"""Unit tests for SchemaRegistry CRUD operations.

Targets k0/gate/schema_registry.py for +33 tests to achieve 100% coverage.
"""

from unittest import mock
from unittest.mock import AsyncMock, MagicMock

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

    async def test_clear_cache(self):
        """Test cache clearing."""
        metrics = mock.Mock()
        registry = SchemaRegistry(metrics_exporter=metrics)

        # Populate cache
        registry._cache = {("test", "1.0"): mock.Mock()}
        registry._loaded = True

        await registry.clear_cache()

        assert registry._cache == {}
        assert registry._loaded is False
        metrics.set_gauge.assert_called_once_with("schema_cache_entries_active", 0.0)


@pytest.fixture
def mock_asyncpg_connection():
    """Mock asyncpg connection for testing."""
    conn = AsyncMock()
    return conn


def _make_mock_row(data: dict):
    """Create a mock row that behaves like asyncpg Record."""
    row = MagicMock()
    row.__getitem__ = MagicMock(side_effect=lambda key: data[key])
    row.keys = MagicMock(return_value=data.keys())
    return row


class TestSchemaRegistryLoad:
    """Test schema loading functionality."""

    async def test_load_empty_registry(self, mock_asyncpg_connection):
        """Test loading from empty schema registry."""
        mock_asyncpg_connection.fetch = AsyncMock(return_value=[])

        registry = SchemaRegistry()

        with mock.patch("k0.gate.schema_registry._resolve_connection") as mock_resolve:
            mock_resolve.return_value.__aenter__ = AsyncMock(return_value=mock_asyncpg_connection)
            mock_resolve.return_value.__aexit__ = AsyncMock(return_value=None)

            await registry.load(connection=mock_asyncpg_connection)

        assert registry._loaded is True
        assert registry._cache == {}

    async def test_load_with_schemas(self, mock_asyncpg_connection):
        """Test loading schemas into cache."""
        mock_row = _make_mock_row(
            {
                "schema_uri": "https://example.com/schemas/test",
                "version": "1.0.0",
                "sha256": "a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
                "status": "ACTIVE",
                "operator_id": "operator@example.com",
                "blocked_ts": None,
                "blocked_reason": None,
                "unblocked_ts": None,
            }
        )

        mock_asyncpg_connection.fetch = AsyncMock(return_value=[mock_row])

        registry = SchemaRegistry()

        with mock.patch("k0.gate.schema_registry._resolve_connection") as mock_resolve:
            mock_resolve.return_value.__aenter__ = AsyncMock(return_value=mock_asyncpg_connection)
            mock_resolve.return_value.__aexit__ = AsyncMock(return_value=None)

            await registry.load(connection=mock_asyncpg_connection)

        assert registry._loaded is True
        assert len(registry._cache) == 1

        key = ("https://example.com/schemas/test", "1.0.0")
        assert key in registry._cache

        record = registry._cache[key]
        assert record.uri == "https://example.com/schemas/test"
        assert record.version == "1.0.0"
        assert record.status == "ACTIVE"
        assert record.operator_id == "operator@example.com"

    async def test_load_with_metrics(self, mock_asyncpg_connection):
        """Test loading with metrics emission."""
        mock_row = _make_mock_row(
            {
                "schema_uri": "https://example.com/schemas/test",
                "version": "1.0.0",
                "sha256": "a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
                "status": "ACTIVE",
                "operator_id": None,
                "blocked_ts": None,
                "blocked_reason": None,
                "unblocked_ts": None,
            }
        )

        mock_asyncpg_connection.fetch = AsyncMock(return_value=[mock_row])

        metrics = mock.Mock()
        registry = SchemaRegistry(metrics_exporter=metrics)

        with mock.patch("k0.gate.schema_registry._resolve_connection") as mock_resolve:
            mock_resolve.return_value.__aenter__ = AsyncMock(return_value=mock_asyncpg_connection)
            mock_resolve.return_value.__aexit__ = AsyncMock(return_value=None)

            await registry.load(connection=mock_asyncpg_connection)

        metrics.set_gauge.assert_called_once_with("schema_cache_entries_active", 1.0)


class TestSchemaRegistryGet:
    """Test schema retrieval functionality."""

    async def test_get_cache_hit(self):
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

        result = await registry.get("https://example.com/schemas/test", "1.0.0")

        assert result == record
        metrics.emit.assert_called_once_with("schema_cache_hits_total")

    async def test_get_cache_miss_found_in_db(self, mock_asyncpg_connection):
        """Test retrieving schema from database when not in cache."""
        mock_row = _make_mock_row(
            {
                "schema_uri": "https://example.com/schemas/test",
                "version": "1.0.0",
                "sha256": "a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
                "status": "ACTIVE",
                "operator_id": "operator@example.com",
                "blocked_ts": "2025-01-15T10:00:00Z",
                "blocked_reason": None,
                "unblocked_ts": None,
            }
        )

        mock_asyncpg_connection.fetchrow = AsyncMock(return_value=mock_row)

        metrics = mock.Mock()
        registry = SchemaRegistry(metrics_exporter=metrics)

        with mock.patch("k0.gate.schema_registry._resolve_connection") as mock_resolve:
            mock_resolve.return_value.__aenter__ = AsyncMock(return_value=mock_asyncpg_connection)
            mock_resolve.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await registry.get(
                "https://example.com/schemas/test", "1.0.0", connection=mock_asyncpg_connection
            )

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

    async def test_get_not_found(self, mock_asyncpg_connection):
        """Test retrieving non-existent schema."""
        mock_asyncpg_connection.fetchrow = AsyncMock(return_value=None)

        registry = SchemaRegistry()

        with mock.patch("k0.gate.schema_registry._resolve_connection") as mock_resolve:
            mock_resolve.return_value.__aenter__ = AsyncMock(return_value=mock_asyncpg_connection)
            mock_resolve.return_value.__aexit__ = AsyncMock(return_value=None)

            with pytest.raises(
                KeyError, match="Schema https://example.com/schemas/test@1.0.0 not found"
            ):
                await registry.get(
                    "https://example.com/schemas/test", "1.0.0", connection=mock_asyncpg_connection
                )


class TestSchemaRegistryRegister:
    """Test schema registration functionality."""

    async def test_register_success(self, mock_asyncpg_connection):
        """Test successful schema registration."""
        mock_asyncpg_connection.execute = AsyncMock(return_value=None)

        registry = SchemaRegistry()

        record = SchemaRecord(
            uri="https://example.com/schemas/test",
            version="1.0.0",
            sha256="a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
            status="REGISTERED",
        )

        with mock.patch("k0.gate.schema_registry._resolve_connection") as mock_resolve:
            mock_resolve.return_value.__aenter__ = AsyncMock(return_value=mock_asyncpg_connection)
            mock_resolve.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await registry.register(record, connection=mock_asyncpg_connection)

        assert result.uri == "https://example.com/schemas/test"
        assert result.version == "1.0.0"
        assert result.status == "REGISTERED"

        # Check cache
        assert ("https://example.com/schemas/test", "1.0.0") in registry._cache

    async def test_register_duplicate(self, mock_asyncpg_connection):
        """Test registration of already existing schema."""
        import asyncpg

        mock_asyncpg_connection.execute = AsyncMock(side_effect=asyncpg.UniqueViolationError(""))

        registry = SchemaRegistry()

        record = SchemaRecord(
            uri="https://example.com/schemas/test",
            version="1.0.0",
            sha256="a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
            status="REGISTERED",
        )

        with mock.patch("k0.gate.schema_registry._resolve_connection") as mock_resolve:
            mock_resolve.return_value.__aenter__ = AsyncMock(return_value=mock_asyncpg_connection)
            mock_resolve.return_value.__aexit__ = AsyncMock(return_value=None)

            with pytest.raises(
                ValueError, match="Schema https://example.com/schemas/test@1.0.0 already exists"
            ):
                await registry.register(record, connection=mock_asyncpg_connection)

    async def test_register_invalid_record(self, mock_asyncpg_connection):
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
            await registry.register(record, connection=mock_asyncpg_connection)


class TestSchemaRegistryUpsert:
    """Test schema upsert functionality."""

    async def test_upsert_insert(self, mock_asyncpg_connection):
        """Test upsert creating new record."""
        mock_asyncpg_connection.execute = AsyncMock(return_value=None)

        registry = SchemaRegistry()

        record = SchemaRecord(
            uri="https://example.com/schemas/test",
            version="1.0.0",
            sha256="a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
            status="REGISTERED",
        )

        with mock.patch("k0.gate.schema_registry._resolve_connection") as mock_resolve:
            mock_resolve.return_value.__aenter__ = AsyncMock(return_value=mock_asyncpg_connection)
            mock_resolve.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await registry.upsert(record, connection=mock_asyncpg_connection)

        assert result.uri == "https://example.com/schemas/test"
        assert result.version == "1.0.0"
        assert result.status == "REGISTERED"

    async def test_upsert_update(self, mock_asyncpg_connection):
        """Test upsert updating existing record."""
        mock_asyncpg_connection.execute = AsyncMock(return_value=None)

        registry = SchemaRegistry()

        # Upsert with updated status
        record = SchemaRecord(
            uri="https://example.com/schemas/test",
            version="1.0.0",
            sha256="b665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
            status="ACTIVE",
        )

        with mock.patch("k0.gate.schema_registry._resolve_connection") as mock_resolve:
            mock_resolve.return_value.__aenter__ = AsyncMock(return_value=mock_asyncpg_connection)
            mock_resolve.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await registry.upsert(record, connection=mock_asyncpg_connection)

        assert result.status == "ACTIVE"


class TestSchemaRegistryPromote:
    """Test schema promotion functionality."""

    async def test_promote_to_active(self, mock_asyncpg_connection):
        """Test promoting a schema to ACTIVE status."""
        mock_fetchrow = _make_mock_row(
            {
                "schema_uri": "https://example.com/schemas/test",
                "version": "1.0.0",
                "sha256": "a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
                "status": "REGISTERED",
            }
        )

        mock_fetch_rows = [
            _make_mock_row(
                {
                    "schema_uri": "https://example.com/schemas/test",
                    "version": "1.0.0",
                    "sha256": "a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
                    "status": "ACTIVE",
                    "operator_id": None,
                    "blocked_ts": None,
                    "blocked_reason": None,
                    "unblocked_ts": None,
                }
            )
        ]

        mock_asyncpg_connection.fetchrow = AsyncMock(return_value=mock_fetchrow)
        mock_asyncpg_connection.fetch = AsyncMock(return_value=mock_fetch_rows)
        mock_asyncpg_connection.execute = AsyncMock(return_value=None)

        registry = SchemaRegistry()

        with mock.patch("k0.gate.schema_registry._resolve_connection") as mock_resolve:
            mock_resolve.return_value.__aenter__ = AsyncMock(return_value=mock_asyncpg_connection)
            mock_resolve.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await registry.promote(
                "https://example.com/schemas/test", "1.0.0", connection=mock_asyncpg_connection
            )

        assert result.status == "ACTIVE"

    async def test_promote_with_demotion(self, mock_asyncpg_connection):
        """Test promoting schema demotes other versions."""
        mock_fetchrow = _make_mock_row(
            {
                "schema_uri": "https://example.com/schemas/test",
                "version": "1.0.0",
                "sha256": "a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
                "status": "REGISTERED",
            }
        )

        # After promotion, all versions returned
        mock_fetch_rows = [
            _make_mock_row(
                {
                    "schema_uri": "https://example.com/schemas/test",
                    "version": "1.0.0",
                    "sha256": "a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
                    "status": "ACTIVE",
                    "operator_id": None,
                    "blocked_ts": None,
                    "blocked_reason": None,
                    "unblocked_ts": None,
                }
            ),
            _make_mock_row(
                {
                    "schema_uri": "https://example.com/schemas/test",
                    "version": "1.1.0",
                    "sha256": "b665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
                    "status": "DEPRECATED",
                    "operator_id": None,
                    "blocked_ts": None,
                    "blocked_reason": None,
                    "unblocked_ts": None,
                }
            ),
            _make_mock_row(
                {
                    "schema_uri": "https://example.com/schemas/test",
                    "version": "2.0.0",
                    "sha256": "c665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
                    "status": "BLOCKED",
                    "operator_id": None,
                    "blocked_ts": None,
                    "blocked_reason": None,
                    "unblocked_ts": None,
                }
            ),
        ]

        mock_asyncpg_connection.fetchrow = AsyncMock(return_value=mock_fetchrow)
        mock_asyncpg_connection.fetch = AsyncMock(return_value=mock_fetch_rows)
        mock_asyncpg_connection.execute = AsyncMock(return_value=None)

        registry = SchemaRegistry()

        with mock.patch("k0.gate.schema_registry._resolve_connection") as mock_resolve:
            mock_resolve.return_value.__aenter__ = AsyncMock(return_value=mock_asyncpg_connection)
            mock_resolve.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await registry.promote(
                "https://example.com/schemas/test", "1.0.0", connection=mock_asyncpg_connection
            )

        assert result.status == "ACTIVE"

        # Check cache has all versions with correct statuses
        assert registry._cache[("https://example.com/schemas/test", "1.0.0")].status == "ACTIVE"
        assert registry._cache[("https://example.com/schemas/test", "1.1.0")].status == "DEPRECATED"
        assert registry._cache[("https://example.com/schemas/test", "2.0.0")].status == "BLOCKED"

    async def test_promote_blocked_schema(self, mock_asyncpg_connection):
        """Test promoting a previously blocked schema."""
        mock_fetchrow = _make_mock_row(
            {
                "schema_uri": "https://example.com/schemas/test",
                "version": "1.0.0",
                "sha256": "a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
                "status": "BLOCKED",
            }
        )

        mock_fetch_rows = [
            _make_mock_row(
                {
                    "schema_uri": "https://example.com/schemas/test",
                    "version": "1.0.0",
                    "sha256": "a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
                    "status": "ACTIVE",
                    "operator_id": "operator@example.com",
                    "blocked_ts": "2025-01-15T10:00:00Z",
                    "blocked_reason": "Security issue",
                    "unblocked_ts": "2025-01-15T12:00:00Z",
                }
            )
        ]

        mock_asyncpg_connection.fetchrow = AsyncMock(return_value=mock_fetchrow)
        mock_asyncpg_connection.fetch = AsyncMock(return_value=mock_fetch_rows)
        mock_asyncpg_connection.execute = AsyncMock(return_value=None)

        registry = SchemaRegistry()

        with mock.patch("k0.gate.schema_registry._resolve_connection") as mock_resolve:
            mock_resolve.return_value.__aenter__ = AsyncMock(return_value=mock_asyncpg_connection)
            mock_resolve.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await registry.promote(
                "https://example.com/schemas/test", "1.0.0", connection=mock_asyncpg_connection
            )

        assert result.status == "ACTIVE"
        assert result.unblocked_ts is not None

    async def test_promote_not_found(self, mock_asyncpg_connection):
        """Test promoting non-existent schema."""
        mock_asyncpg_connection.fetchrow = AsyncMock(return_value=None)

        registry = SchemaRegistry()

        with mock.patch("k0.gate.schema_registry._resolve_connection") as mock_resolve:
            mock_resolve.return_value.__aenter__ = AsyncMock(return_value=mock_asyncpg_connection)
            mock_resolve.return_value.__aexit__ = AsyncMock(return_value=None)

            with pytest.raises(
                KeyError, match="Schema https://example.com/schemas/test@1.0.0 not found"
            ):
                await registry.promote(
                    "https://example.com/schemas/test", "1.0.0", connection=mock_asyncpg_connection
                )


class TestSchemaRegistryBlock:
    """Test schema blocking functionality."""

    async def test_block_success(self, mock_asyncpg_connection):
        """Test successful schema blocking."""
        mock_fetch_rows = [
            _make_mock_row(
                {
                    "schema_uri": "https://example.com/schemas/test",
                    "version": "1.0.0",
                    "sha256": "a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
                    "status": "BLOCKED",
                    "operator_id": "operator@example.com",
                    "blocked_ts": "2025-01-15T10:00:00Z",
                    "blocked_reason": "Security vulnerability",
                    "unblocked_ts": None,
                }
            )
        ]

        mock_asyncpg_connection.execute = AsyncMock(return_value="UPDATE 1")
        mock_asyncpg_connection.fetch = AsyncMock(return_value=mock_fetch_rows)

        registry = SchemaRegistry()

        with mock.patch("k0.gate.schema_registry._resolve_connection") as mock_resolve:
            mock_resolve.return_value.__aenter__ = AsyncMock(return_value=mock_asyncpg_connection)
            mock_resolve.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await registry.block(
                "https://example.com/schemas/test",
                "1.0.0",
                operator_id="operator@example.com",
                reason="Security vulnerability",
                connection=mock_asyncpg_connection,
            )

        assert result.status == "BLOCKED"
        assert result.operator_id == "operator@example.com"
        assert result.blocked_reason == "Security vulnerability"
        assert result.blocked_ts is not None
        assert result.unblocked_ts is None

    async def test_block_empty_operator_id(self, mock_asyncpg_connection):
        """Test blocking with empty operator_id."""
        registry = SchemaRegistry()

        with pytest.raises(ValueError, match="operator_id is required for block operations"):
            await registry.block(
                "https://example.com/schemas/test",
                "1.0.0",
                operator_id="",
                reason="Security issue",
                connection=mock_asyncpg_connection,
            )

    async def test_block_empty_reason(self, mock_asyncpg_connection):
        """Test blocking with empty reason."""
        registry = SchemaRegistry()

        with pytest.raises(ValueError, match="reason is required for block operations"):
            await registry.block(
                "https://example.com/schemas/test",
                "1.0.0",
                operator_id="operator@example.com",
                reason="",
                connection=mock_asyncpg_connection,
            )

    async def test_block_not_found(self, mock_asyncpg_connection):
        """Test blocking non-existent schema."""
        mock_asyncpg_connection.execute = AsyncMock(return_value="UPDATE 0")

        registry = SchemaRegistry()

        with mock.patch("k0.gate.schema_registry._resolve_connection") as mock_resolve:
            mock_resolve.return_value.__aenter__ = AsyncMock(return_value=mock_asyncpg_connection)
            mock_resolve.return_value.__aexit__ = AsyncMock(return_value=None)

            with pytest.raises(
                KeyError, match="Schema https://example.com/schemas/test@1.0.0 not found"
            ):
                await registry.block(
                    "https://example.com/schemas/test",
                    "1.0.0",
                    operator_id="operator@example.com",
                    reason="Security issue",
                    connection=mock_asyncpg_connection,
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

    async def test_get_audit_trail_all(self, mock_asyncpg_connection):
        """Test retrieving complete audit trail."""
        mock_fetch_rows = [
            _make_mock_row(
                {
                    "schema_uri": "https://example.com/schemas/test",
                    "version": "1.0.0",
                    "sha256": "a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
                    "status": "ACTIVE",
                    "operator_id": "op1@example.com",
                    "blocked_ts": None,
                    "blocked_reason": None,
                    "unblocked_ts": None,
                }
            ),
            _make_mock_row(
                {
                    "schema_uri": "https://example.com/schemas/test",
                    "version": "1.1.0",
                    "sha256": "b665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
                    "status": "BLOCKED",
                    "operator_id": "op2@example.com",
                    "blocked_ts": "2025-01-15T10:00:00Z",
                    "blocked_reason": "Security",
                    "unblocked_ts": None,
                }
            ),
        ]

        mock_asyncpg_connection.fetch = AsyncMock(return_value=mock_fetch_rows)

        registry = SchemaRegistry()

        with mock.patch("k0.gate.schema_registry._resolve_connection") as mock_resolve:
            mock_resolve.return_value.__aenter__ = AsyncMock(return_value=mock_asyncpg_connection)
            mock_resolve.return_value.__aexit__ = AsyncMock(return_value=None)

            audit_trail = list(await registry.get_audit_trail(connection=mock_asyncpg_connection))

        assert len(audit_trail) == 2

    async def test_get_audit_trail_filtered_by_uri(self, mock_asyncpg_connection):
        """Test audit trail filtered by URI."""
        mock_fetch_rows = [
            _make_mock_row(
                {
                    "schema_uri": "https://example.com/schemas/test",
                    "version": "1.0.0",
                    "sha256": "a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
                    "status": "ACTIVE",
                    "operator_id": None,
                    "blocked_ts": None,
                    "blocked_reason": None,
                    "unblocked_ts": None,
                }
            ),
        ]

        mock_asyncpg_connection.fetch = AsyncMock(return_value=mock_fetch_rows)

        registry = SchemaRegistry()

        with mock.patch("k0.gate.schema_registry._resolve_connection") as mock_resolve:
            mock_resolve.return_value.__aenter__ = AsyncMock(return_value=mock_asyncpg_connection)
            mock_resolve.return_value.__aexit__ = AsyncMock(return_value=None)

            audit_trail = list(
                await registry.get_audit_trail(
                    uri="https://example.com/schemas/test", connection=mock_asyncpg_connection
                )
            )

        assert len(audit_trail) == 1
        assert audit_trail[0].uri == "https://example.com/schemas/test"

    async def test_get_audit_trail_filtered_by_status(self, mock_asyncpg_connection):
        """Test audit trail filtered by status."""
        mock_fetch_rows = [
            _make_mock_row(
                {
                    "schema_uri": "https://example.com/schemas/test",
                    "version": "1.1.0",
                    "sha256": "a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
                    "status": "BLOCKED",
                    "operator_id": None,
                    "blocked_ts": None,
                    "blocked_reason": None,
                    "unblocked_ts": None,
                }
            ),
        ]

        mock_asyncpg_connection.fetch = AsyncMock(return_value=mock_fetch_rows)

        registry = SchemaRegistry()

        with mock.patch("k0.gate.schema_registry._resolve_connection") as mock_resolve:
            mock_resolve.return_value.__aenter__ = AsyncMock(return_value=mock_asyncpg_connection)
            mock_resolve.return_value.__aexit__ = AsyncMock(return_value=None)

            audit_trail = list(
                await registry.get_audit_trail(status="BLOCKED", connection=mock_asyncpg_connection)
            )

        assert len(audit_trail) == 1
        assert audit_trail[0].status == "BLOCKED"

    async def test_get_audit_trail_version_requires_uri(self, mock_asyncpg_connection):
        """Test that version filter requires URI."""
        registry = SchemaRegistry()

        with pytest.raises(ValueError, match="version filter requires uri parameter"):
            await registry.get_audit_trail(version="1.0.0", connection=mock_asyncpg_connection)


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

    async def test_store_record(self):
        """Test storing record in cache."""
        registry = SchemaRegistry()

        record = SchemaRecord(
            uri="https://example.com/schemas/test",
            version="1.0.0",
            sha256="a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
            status="ACTIVE",
        )

        await registry._store(record)

        assert registry._loaded is True
        assert ("https://example.com/schemas/test", "1.0.0") in registry._cache
        assert registry._cache[("https://example.com/schemas/test", "1.0.0")] == record

    async def test_refresh_uri_cache(self):
        """Test refreshing cache for a specific URI."""
        registry = SchemaRegistry()

        # Setup initial cache
        old_record = SchemaRecord("https://example.com/schemas/test", "1.0.0", "old_sha", "ACTIVE")
        registry._cache[("https://example.com/schemas/test", "1.0.0")] = old_record

        # Mock rows from database
        mock_rows = [
            _make_mock_row(
                {
                    "schema_uri": "https://example.com/schemas/test",
                    "version": "1.0.0",
                    "sha256": "new_sha",
                    "status": "BLOCKED",
                    "operator_id": "operator@example.com",
                    "blocked_ts": "2025-01-15T10:00:00Z",
                    "blocked_reason": "Updated",
                    "unblocked_ts": None,
                }
            ),
            _make_mock_row(
                {
                    "schema_uri": "https://example.com/schemas/test",
                    "version": "1.1.0",
                    "sha256": "sha2",
                    "status": "ACTIVE",
                    "operator_id": None,
                    "blocked_ts": None,
                    "blocked_reason": None,
                    "unblocked_ts": None,
                }
            ),
        ]

        await registry._refresh_uri_cache("https://example.com/schemas/test", mock_rows)

        # Check cache was updated
        assert len(registry._cache) == 2
        assert ("https://example.com/schemas/test", "1.0.0") in registry._cache
        assert ("https://example.com/schemas/test", "1.1.0") in registry._cache

        updated_record = registry._cache[("https://example.com/schemas/test", "1.0.0")]
        assert updated_record.sha256 == "new_sha"
        assert updated_record.status == "BLOCKED"
        assert updated_record.operator_id == "operator@example.com"
