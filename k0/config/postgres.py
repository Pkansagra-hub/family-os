"""PostgreSQL configuration for K0 kernel.

Part of Milestone 1.1.1 - Issue 1.1.1.5: PostgreSQL Environment Configuration.

This module provides Pydantic-based configuration for PostgreSQL connections,
with support for:
- asyncpg connection pooling
- pgbouncer compatibility (statement_cache_size=0)
- SSL/TLS configuration
- pgvector extension settings
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings


class PostgresSettings(BaseSettings):
    """PostgreSQL connection settings with pgbouncer support.

    Environment variables are prefixed with K0_POSTGRES_.
    Example: K0_POSTGRES_HOST=localhost

    Attributes:
        host: PostgreSQL host (or pgbouncer host in production)
        port: PostgreSQL port (5432 direct, 6432 via pgbouncer)
        database: Database name
        user: Database user
        password: Database password (SecretStr for security)
        min_pool_size: Minimum connections in asyncpg pool
        max_pool_size: Maximum connections in asyncpg pool
        ssl_mode: SSL connection mode
        ssl_root_cert: Path to SSL root certificate
        vector_dimensions: Default vector dimensions for pgvector
        statement_cache_size: Prepared statement cache (0 for pgbouncer)
        command_timeout: Query timeout in seconds
    """

    model_config = {"env_prefix": "K0_POSTGRES_"}

    # Connection settings
    host: str = Field(
        default="localhost",
        description="PostgreSQL host (use pgbouncer host in production)",
    )
    port: int = Field(
        default=5432,
        ge=1,
        le=65535,
        description="PostgreSQL port (5432 direct, 6432 via pgbouncer)",
    )
    database: str = Field(
        default="k0_kernel",
        min_length=1,
        alias="db",
        description="Database name",
    )
    user: str = Field(
        default="k0user",
        min_length=1,
        description="Database user",
    )
    password: SecretStr = Field(
        default=SecretStr("changeme"),
        description="Database password",
    )

    # Connection pool settings (for asyncpg.Pool)
    min_pool_size: int = Field(
        default=5,
        ge=1,
        le=100,
        description="Minimum connections in asyncpg pool",
    )
    max_pool_size: int = Field(
        default=25,
        ge=1,
        le=200,
        description="Maximum connections in asyncpg pool",
    )

    # SSL settings
    ssl_mode: Literal["disable", "allow", "prefer", "require", "verify-ca", "verify-full"] = Field(
        default="prefer",
        description="SSL connection mode",
    )
    ssl_root_cert: str | None = Field(
        default=None,
        description="Path to SSL root certificate (for verify-ca/verify-full)",
    )

    # pgvector settings
    vector_dimensions: int = Field(
        default=768,
        ge=1,
        le=16000,
        description="Default vector dimensions for embedding columns",
    )

    # asyncpg settings (for pgbouncer compatibility)
    statement_cache_size: int = Field(
        default=0,
        ge=0,
        description="Prepared statement cache size (0 for pgbouncer transaction mode)",
    )
    command_timeout: float = Field(
        default=60.0,
        ge=0,
        description="Query timeout in seconds (0 = no timeout)",
    )
    max_inactive_connection_lifetime: float = Field(
        default=300.0,
        ge=0,
        description="Close inactive connections after this many seconds",
    )

    @field_validator("max_pool_size")
    @classmethod
    def validate_pool_sizes(cls, v: int, info) -> int:
        """Ensure max_pool_size >= min_pool_size."""
        min_size = info.data.get("min_pool_size", 5)
        if v < min_size:
            raise ValueError(f"max_pool_size ({v}) must be >= min_pool_size ({min_size})")
        return v

    @property
    def dsn(self) -> str:
        """Build asyncpg-compatible DSN.

        Format: postgresql://user:password@host:port/database

        Returns:
            Connection string for asyncpg.connect() or asyncpg.create_pool()
        """
        pwd = self.password.get_secret_value()
        return f"postgresql://{self.user}:{pwd}@{self.host}:{self.port}/{self.database}"

    @property
    def dsn_masked(self) -> str:
        """DSN with password masked for logging.

        Returns:
            Connection string with password replaced by ***
        """
        return f"postgresql://{self.user}:***@{self.host}:{self.port}/{self.database}"

    @property
    def asyncpg_pool_config(self) -> dict:
        """Configuration dict for asyncpg.create_pool().

        Returns:
            Dictionary of asyncpg pool configuration options.

        Note:
            statement_cache_size=0 is CRITICAL for pgbouncer transaction mode.
            See ADR-0XXX: PostgreSQL Migration for details.
        """
        return {
            "dsn": self.dsn,
            "min_size": self.min_pool_size,
            "max_size": self.max_pool_size,
            "statement_cache_size": self.statement_cache_size,
            "command_timeout": self.command_timeout,
            "max_inactive_connection_lifetime": self.max_inactive_connection_lifetime,
        }


class DatabaseSettings(BaseSettings):
    """Top-level database configuration with backend selection.

    Provides feature flag for gradual PostgreSQL rollout.

    Environment variables:
        K0_USE_POSTGRESQL: Set to "true" to use PostgreSQL (default after migration)
        K0_DB_PATH: SQLite path (deprecated, for rollback only)
    """

    model_config = {"env_prefix": "K0_"}

    # Feature flag for PostgreSQL migration
    use_postgresql: bool = Field(
        default=True,
        alias="USE_POSTGRESQL",
        description="Use PostgreSQL instead of SQLite",
    )

    # PostgreSQL settings (used when use_postgresql=True)
    postgres: PostgresSettings = Field(default_factory=PostgresSettings)

    # SQLite settings (deprecated, for rollback only)
    db_path: str = Field(
        default="/data/k0_runtime.sqlite3",
        alias="DB_PATH",
        description="SQLite database path (deprecated)",
    )

    @property
    def backend(self) -> str:
        """Return current database backend identifier."""
        return "postgresql" if self.use_postgresql else "sqlite"


# Singleton instance for global access
_settings: DatabaseSettings | None = None


def get_database_settings() -> DatabaseSettings:
    """Get or create the global database settings instance."""
    global _settings
    if _settings is None:
        _settings = DatabaseSettings()
    return _settings


def get_postgres_settings() -> PostgresSettings:
    """Convenience function to get PostgreSQL settings directly."""
    return get_database_settings().postgres
