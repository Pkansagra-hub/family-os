"""Neo4j migration runner for K0 knowledge graph schema.

This module provides forward migration support with dry-run validation and
Prometheus telemetry. Migrations are applied in alphabetical order using Cypher
DDL statements (constraints, indexes).

Version tracking is stored in Neo4j as (:SchemaVersion) nodes to ensure
idempotency across restarts.

Telemetry (requires prometheus_client to be installed):
  - k0_neo4j_migration_duration_seconds: Duration of migration application (histogram)
  - k0_neo4j_migration_status: Last migration status (gauge: 1=success, 0=pending, -1=error)

Example:
  # Apply forward migrations
  results = apply_cypher_migrations(
      uri="neo4j://localhost:7687",
      username="neo4j",
      password="password",
      database="neo4j",
  )

  # Dry-run mode
  results = apply_cypher_migrations(
      uri="neo4j://localhost:7687",
      username="neo4j",
      password="password",
      database="neo4j",
      dry_run=True,
  )
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

LOGGER = logging.getLogger(__name__)

_DEFAULT_MIGRATIONS_DIR = (
    Path(__file__).resolve().parents[1] / "contracts" / "cypher" / "migrations"
)

# Prometheus telemetry (optional, graceful degradation if not installed)
try:
    from prometheus_client import Gauge, Histogram

    _migration_duration_histogram = Histogram(
        "k0_neo4j_migration_duration_seconds",
        "Duration of Neo4j migration application in seconds",
        buckets=(0.1, 0.5, 1.0, 2.5, 5.0),
    )
    _migration_status_gauge = Gauge(
        "k0_neo4j_migration_status",
        "Last Neo4j migration status: 1=success, 0=pending, -1=error",
    )
    _TELEMETRY_ENABLED = True
except ImportError:
    _TELEMETRY_ENABLED = False


class Neo4jMigrationError(RuntimeError):
    """Raised when a Neo4j migration fails or the migration graph is inconsistent."""


@dataclass(slots=True)
class Neo4jMigrationResult:
    """Represents the outcome of evaluating a Neo4j migration file.

    Attributes
    ----------
    version : str
        Version identifier (e.g., "0001_baseline")
    action : str
        One of {"applied", "skipped", "pending"}
    checksum : str
        SHA256 hash of the migration script
    path : Path
        Filesystem path to the migration file
    duration_seconds : float | None
        Time taken to apply migration, or None if skipped
    """

    version: str
    action: str  # one of {"applied", "skipped", "pending"}
    checksum: str
    path: Path
    duration_seconds: float | None = None


def apply_cypher_migrations(
    uri: str,
    username: str,
    password: str,
    database: str = "neo4j",
    *,
    migrations_path: Path | str | None = None,
    dry_run: bool = False,
    logger: logging.Logger | None = None,
) -> list[Neo4jMigrationResult]:
    """Apply Neo4j Cypher migrations to the knowledge graph.

    Migrations are applied in alphabetical order. Each migration is wrapped in a
    transaction and recorded as a (:SchemaVersion) node for idempotency tracking.

    Parameters
    ----------
    uri:
        Neo4j connection URI (e.g., "neo4j://localhost:7687")
    username:
        Neo4j authentication username
    password:
        Neo4j authentication password
    database:
        Neo4j database name (default: "neo4j")
    migrations_path:
        Directory containing ``*.cypher`` migration files. Defaults to the
        repository's ``k0/contracts/cypher/migrations`` directory.
    dry_run:
        When true, migrations are not executed but their pending status is
        reported. No SchemaVersion nodes are created.
    logger:
        Optional logger instance to emit progress messages.

    Returns
    -------
    list[Neo4jMigrationResult]
        Ordered list describing whether each migration was applied, skipped, or
        remains pending when running in dry-run mode. Includes duration_seconds
        for applied migrations (for telemetry).

    Raises
    ------
    Neo4jMigrationError
        If migration directory doesn't exist, no migrations found, or a migration
        fails to apply (due to Cypher syntax errors or checksum mismatch).
    """

    log = logger or LOGGER
    migrations_dir = Path(migrations_path) if migrations_path else _DEFAULT_MIGRATIONS_DIR

    if not migrations_dir.exists():
        raise Neo4jMigrationError(f"Migration directory does not exist: {migrations_dir}")
    if not migrations_dir.is_dir():
        raise Neo4jMigrationError(f"Migration path is not a directory: {migrations_dir}")

    migration_files = sorted(p for p in migrations_dir.glob("*.cypher") if p.is_file())
    if not migration_files:
        raise Neo4jMigrationError(f"No migration files found in {migrations_dir}")

    results: list[Neo4jMigrationResult] = []

    # Import neo4j driver (graceful failure if not installed)
    try:
        from neo4j import GraphDatabase
    except ImportError as exc:
        raise Neo4jMigrationError(
            "neo4j driver not installed. Install with: pip install neo4j"
        ) from exc

    driver = GraphDatabase.driver(uri, auth=(username, password))
    try:
        with driver.session(database=database) as session:
            # Ensure SchemaVersion constraint exists
            _ensure_schema_version_constraint(session)

            # Load applied migrations
            applied = _load_applied_migrations(session)

            for migration_path in migration_files:
                version = migration_path.stem
                script = migration_path.read_text(encoding="utf-8")
                checksum = hashlib.sha256(script.encode("utf-8")).hexdigest()

                if version in applied:
                    recorded_checksum = applied[version]
                    if recorded_checksum != checksum:
                        raise Neo4jMigrationError(
                            (
                                "Checksum mismatch for migration "
                                f"'{version}'. Expected {recorded_checksum}, found {checksum}"
                            )
                        )
                    results.append(
                        Neo4jMigrationResult(
                            version=version,
                            action="skipped",
                            checksum=checksum,
                            path=migration_path,
                        )
                    )
                    continue

                if dry_run:
                    log.info("[dry-run] would apply migration %s", version)
                    results.append(
                        Neo4jMigrationResult(
                            version=version,
                            action="pending",
                            checksum=checksum,
                            path=migration_path,
                        )
                    )
                    continue

                log.info("Applying Neo4j migration %s", version)
                start_time = datetime.now(timezone.utc)
                try:
                    # Execute migration script (Cypher DDL)
                    # Note: Neo4j doesn't allow mixing DDL (CREATE CONSTRAINT/INDEX) with DML (CREATE nodes)
                    # We need separate transactions for schema modifications and version tracking
                    statements = _split_cypher_statements(script)

                    # Transaction 1: Apply schema modifications (DDL)
                    def _apply_schema_ddl_tx(tx):
                        for stmt in statements:
                            stmt_stripped = stmt.strip()
                            if stmt_stripped and not stmt_stripped.startswith("//"):
                                tx.run(stmt_stripped)

                    session.execute_write(_apply_schema_ddl_tx)

                    # Transaction 2: Record migration in SchemaVersion (DML)
                    def _record_migration_tx(tx):
                        tx.run(
                            """
                            CREATE (v:SchemaVersion {
                                version: $version,
                                checksum: $checksum,
                                applied_at: datetime($applied_at)
                            })
                            """,
                            version=version,
                            checksum=checksum,
                            applied_at=_utc_timestamp(),
                        )

                    session.execute_write(_record_migration_tx)

                except Exception as exc:  # pragma: no cover - defensive error handling
                    if _TELEMETRY_ENABLED:
                        _migration_status_gauge.set(-1)
                    raise Neo4jMigrationError(f"Failed to apply migration {version}") from exc

                duration_seconds = (datetime.now(timezone.utc) - start_time).total_seconds()
                if _TELEMETRY_ENABLED:
                    _migration_duration_histogram.observe(duration_seconds)
                    _migration_status_gauge.set(1)

                results.append(
                    Neo4jMigrationResult(
                        version=version,
                        action="applied",
                        checksum=checksum,
                        path=migration_path,
                        duration_seconds=duration_seconds,
                    )
                )

    finally:
        driver.close()

    return results


def _ensure_schema_version_constraint(session) -> None:
    """Create uniqueness constraint for SchemaVersion.version if it doesn't exist."""
    # Check if constraint exists (Neo4j 5.x syntax)
    result = session.run("SHOW CONSTRAINTS")
    constraint_names = {record["name"] for record in result}

    if "schema_version_unique" not in constraint_names:
        session.run(
            """
            CREATE CONSTRAINT schema_version_unique IF NOT EXISTS
            FOR (v:SchemaVersion) REQUIRE v.version IS UNIQUE
            """
        )


def _load_applied_migrations(session) -> dict[str, str]:
    """Load all applied migrations from SchemaVersion nodes."""
    result = session.run(
        """
        MATCH (v:SchemaVersion)
        RETURN v.version AS version, v.checksum AS checksum
        """
    )
    return {record["version"]: record["checksum"] for record in result}


def _split_cypher_statements(script: str) -> list[str]:
    """Split Cypher script into individual statements by semicolon.

    This is a simple implementation that splits on semicolons. For production,
    consider a proper Cypher parser if statements contain semicolons in strings.
    """
    # Remove single-line comments (// ...)
    lines = []
    for line in script.split("\n"):
        # Strip inline comments
        if "//" in line:
            line = line[: line.index("//")]
        lines.append(line)

    script_cleaned = "\n".join(lines)

    # Split by semicolon
    statements = [s.strip() for s in script_cleaned.split(";") if s.strip()]
    return statements


def _utc_timestamp() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


__all__ = [
    "Neo4jMigrationError",
    "Neo4jMigrationResult",
    "apply_cypher_migrations",
]
