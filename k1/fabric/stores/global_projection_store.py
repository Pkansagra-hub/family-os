"""GlobalProjectionStore — shared SQLite store for capabilities, connectors, graph ontology.

Phase 1, Epic 1 (Issues 1.1–1.4).  The single source of truth for all
capability contracts, connector manifests, constitutions, resource kinds,
and the 6 graph ontology tables that power typed resolution.

Design authority: ``k1/fabric/docs/phase1_implementation_plan.md`` Epics 1.1–1.4.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Issue 1.1 — Record dataclasses (return types for all query methods)
# ---------------------------------------------------------------------------


@dataclass
class ConnectorRecord:
    connector_id: str
    label: str
    connector_type: str  # 'native' | 'bridge' | 'ifl'
    provider_type: str  # 'LOCAL' | 'MCP' | 'BRIDGE' | 'AGENT' | 'WORKFLOW'
    version: str
    admission_verdict: str  # 'admitted' | 'pending' | 'rejected'
    registration_type: str  # 'static' | 'dynamic' | 'discovered'
    constitution: dict = field(default_factory=dict)
    policy_declarations: dict = field(default_factory=dict)
    resource_kinds: list[str] = field(default_factory=list)
    guide_cards: list[dict] = field(default_factory=list)  # Phase 1.1 (Epic 9.5)
    created_at: str = ""
    updated_at: str = ""


@dataclass
class CapabilityRecord:
    capability_name: str  # "tool.execute.family.calendar.create"
    connector_id: str  # "family.calendar"
    invocation_mode: str  # 'read' | 'execute'
    action_name: str  # 'list' | 'search' | 'create' | 'update' | 'delete' | 'send'
    effect: str  # 'read' | 'write' | 'delete' | 'compute'
    resource_kind: str | None  # "calendar_event"
    description: str = ""
    required_inputs: list[dict] = field(default_factory=list)
    optional_inputs: list[dict] = field(default_factory=list)
    output_schema_ref: str | None = None
    safety_band_min: str = "GREEN"
    risk_class: str = "benign"
    idempotency: str | None = None  # 'safe' | 'unsafe' | None
    compensation_capability: str | None = None
    record_type: str = "executable_capability"
    created_at: str = ""
    contract_json: dict = field(default_factory=dict)
    synthetic: bool = False

    # NOTE: capability_name is the single PK in the capabilities table.
    # Multi-resource projection lives in capability_type_index, which has
    # one row per (capability_name, resource_family, operation_family, effect).
    # Do NOT create duplicate capability rows per resource_kind.


@dataclass
class ResourceKindRecord:
    kind_id: str  # e.g. 'calendar.event', 'task.item'
    connector_id: str
    label: str
    schema: dict = field(default_factory=dict)
    verifier_affordances: list[str] = field(default_factory=list)
    created_at: str = ""


@dataclass
class ConstitutionRecord:
    connector_id: str
    constitution_id: str
    schema_version: str = "1.0.0"
    authored_by: str | None = None
    authored_at: str | None = None
    last_proven_at: str | None = None
    execution_phases: list[str] = field(default_factory=list)
    prerequisite_reads: list[dict] = field(default_factory=list)
    conflict_analysis_rules: list[dict] = field(default_factory=list)
    hil_gates: list[dict] = field(default_factory=list)
    mutation_sequencing: list[dict] = field(default_factory=list)
    verification_requirements: list[dict] = field(default_factory=list)
    companion_resource_roles: list[dict] = field(default_factory=list)
    precondition_summary: str | None = None
    companion_resource_summary: str | None = None
    hil_trigger_summary: str | None = None
    degradation_policy: str | None = None


# ---------------------------------------------------------------------------
# LoadResult — returned by load_from_manifest_batch
# ---------------------------------------------------------------------------


@dataclass
class LoadResult:
    total_connectors: int
    total_capabilities: int
    admitted: int
    rejected: int
    errors: list[str] = field(default_factory=list)


@dataclass
class CapabilityRegistrationBatch:
    """Batch of capabilities to register together (used by load_from_manifest_batch)."""

    connector: ConnectorRecord
    capabilities: list[CapabilityRecord]
    resource_kinds: list[ResourceKindRecord] = field(default_factory=list)
    constitution: ConstitutionRecord | None = None


# ---------------------------------------------------------------------------
# GlobalProjectionStore
# ---------------------------------------------------------------------------


class GlobalProjectionStore:
    """Shared SQLite store for all capability contracts, connectors, graph ontology.

    Thread safety: SQLite WAL mode + check_same_thread=False.
    Writes are serialised by CapabilityRegistryAPI — no additional mutex needed.
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None

    # ── Lifecycle ────────────────────────────────────────────────────────

    def open(self) -> None:
        """Open the database in WAL mode and ensure the schema exists."""
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._ensure_schema()
        self._conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @property
    def _db(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("GlobalProjectionStore is not open")
        return self._conn

    # ── Issue 1.2 — SQL Schema ──────────────────────────────────────────

    def _ensure_schema(self) -> None:
        """Create all tables and indexes if they do not exist.

        10 data tables + 1 FTS5 virtual table + 1 index.
        """
        db = self._db

        # 1. Connectors
        db.execute("""
            CREATE TABLE IF NOT EXISTS connectors (
                connector_id    TEXT PRIMARY KEY,
                label           TEXT NOT NULL,
                connector_type  TEXT NOT NULL CHECK(connector_type IN ('native','bridge','ifl')),
                provider_type   TEXT NOT NULL,
                version         TEXT NOT NULL DEFAULT '1.0.0',
                admission_verdict TEXT NOT NULL CHECK(admission_verdict IN ('admitted','pending','rejected')),
                registration_type TEXT NOT NULL CHECK(registration_type IN ('static','dynamic','discovered')),
                constitution_json TEXT NOT NULL DEFAULT '{}',
                policy_json     TEXT NOT NULL DEFAULT '{}',
                resource_kinds_json TEXT NOT NULL DEFAULT '[]',
                guide_cards_json TEXT NOT NULL DEFAULT '[]',
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL
            )
            """)

        # Migration: add guide_cards_json to connectors for databases created
        # before Phase 1.1 (Epic 9.5).  ALTER is a no-op when the column is
        # already present (fresh databases get it from the CREATE TABLE above).
        connector_cols = {r[1] for r in db.execute("PRAGMA table_info(connectors)").fetchall()}
        if "guide_cards_json" not in connector_cols:
            db.execute(
                "ALTER TABLE connectors ADD COLUMN " "guide_cards_json TEXT NOT NULL DEFAULT '[]'"
            )

        # 2. Capabilities
        db.execute("""
            CREATE TABLE IF NOT EXISTS capabilities (
                capability_name TEXT PRIMARY KEY,
                connector_id    TEXT NOT NULL REFERENCES connectors(connector_id) ON DELETE CASCADE,
                invocation_mode TEXT NOT NULL CHECK(invocation_mode IN ('read','execute')),
                action_name     TEXT NOT NULL,
                effect          TEXT NOT NULL CHECK(effect IN ('read','write','delete','compute')),
                resource_kind   TEXT,
                description     TEXT NOT NULL DEFAULT '',
                required_inputs_json TEXT NOT NULL DEFAULT '[]',
                optional_inputs_json TEXT NOT NULL DEFAULT '[]',
                output_schema_ref   TEXT,
                safety_band_min TEXT NOT NULL DEFAULT 'GREEN' CHECK(safety_band_min IN ('GREEN','AMBER','RED')),
                risk_class      TEXT NOT NULL DEFAULT 'benign',
                idempotency     TEXT CHECK(idempotency IS NULL OR idempotency IN ('safe','unsafe')),
                compensation_capability TEXT,
                record_type     TEXT NOT NULL CHECK(record_type IN ('executable_capability','activity_profile','workflow','agent')),
                created_at      TEXT NOT NULL,
                contract_json   TEXT NOT NULL,
                synthetic       INTEGER NOT NULL DEFAULT 0
            )
            """)
        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_capability_lookup
                ON capabilities(resource_kind, invocation_mode, effect, connector_id, record_type, safety_band_min)
            """)

        # 3. FTS5 full-text search
        db.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS capabilities_fts USING fts5(
                capability_name, description, resource_kind, connector_id,
                content='capabilities', content_rowid='rowid'
            )
            """)

        # 4. Resource kinds
        db.execute("""
            CREATE TABLE IF NOT EXISTS resource_kinds (
                kind_id         TEXT PRIMARY KEY,
                connector_id    TEXT NOT NULL REFERENCES connectors(connector_id),
                label           TEXT NOT NULL,
                schema_json     TEXT NOT NULL DEFAULT '{}',
                verifier_affordances_json TEXT NOT NULL DEFAULT '[]',
                created_at      TEXT NOT NULL
            )
            """)

        # 5. Connector constitutions (per-connector, not per-operation)
        db.execute("""
            CREATE TABLE IF NOT EXISTS connector_constitutions (
                connector_id        TEXT PRIMARY KEY REFERENCES connectors(connector_id),
                constitution_id     TEXT NOT NULL,
                schema_version      TEXT NOT NULL DEFAULT '1.0.0',
                authored_by         TEXT,
                authored_at         TEXT,
                last_proven_at      TEXT,
                execution_phases_json       TEXT NOT NULL DEFAULT '[]',
                prerequisite_reads_json     TEXT NOT NULL DEFAULT '[]',
                conflict_analysis_rules_json TEXT NOT NULL DEFAULT '[]',
                hil_gates_json              TEXT NOT NULL DEFAULT '[]',
                mutation_sequencing_json    TEXT NOT NULL DEFAULT '[]',
                verification_requirements_json TEXT NOT NULL DEFAULT '[]',
                companion_resource_roles_json  TEXT NOT NULL DEFAULT '[]',
                precondition_summary        TEXT,
                companion_resource_summary  TEXT,
                hil_trigger_summary         TEXT,
                degradation_policy          TEXT
            )
            """)

        # 6–11. Graph ontology tables
        db.execute("""
            CREATE TABLE IF NOT EXISTS concept_aliases (
                alias TEXT NOT NULL, canonical_concept TEXT NOT NULL, domain TEXT,
                weight REAL DEFAULT 1.0, generic INTEGER DEFAULT 0, source TEXT DEFAULT 'catalog',
                PRIMARY KEY(alias, canonical_concept, domain)
            )
            """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS concept_resource_edges (
                concept TEXT NOT NULL, resource_family TEXT NOT NULL, domain TEXT NOT NULL,
                weight REAL DEFAULT 1.0,
                PRIMARY KEY(concept, resource_family, domain)
            )
            """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS resource_connector_edges (
                domain TEXT NOT NULL, resource_family TEXT NOT NULL, connector_id TEXT NOT NULL,
                weight REAL DEFAULT 1.0,
                role TEXT NOT NULL DEFAULT 'primary'
                    CHECK(role IN ('primary','companion','verifier','prerequisite')),
                PRIMARY KEY(domain, resource_family, connector_id)
            )
            """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS operation_equivalences (
                canonical_operation TEXT NOT NULL,
                equivalent_operation TEXT NOT NULL,
                resource_family TEXT NOT NULL DEFAULT '',
                domain TEXT NOT NULL DEFAULT '',
                PRIMARY KEY(canonical_operation, equivalent_operation, resource_family, domain)
            )
            """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS operation_aliases (
                alias TEXT NOT NULL, operation_family TEXT NOT NULL, effect TEXT NOT NULL,
                weight REAL DEFAULT 1.0, generic INTEGER DEFAULT 1,
                PRIMARY KEY(alias, operation_family)
            )
            """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS capability_type_index (
                capability_name TEXT NOT NULL, connector_id TEXT NOT NULL, domain TEXT NOT NULL,
                resource_family TEXT NOT NULL, operation_family TEXT NOT NULL, effect TEXT NOT NULL,
                side_effect_class TEXT, risk_class TEXT,
                PRIMARY KEY(capability_name, resource_family, operation_family, effect)
            )
            """)

    # ── Issue 1.3 — Connector CRUD ──────────────────────────────────────

    def upsert_connector(self, connector: ConnectorRecord) -> None:
        self._db.execute(
            """
            INSERT INTO connectors (connector_id, label, connector_type, provider_type, version,
                admission_verdict, registration_type, constitution_json, policy_json,
                resource_kinds_json, guide_cards_json, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(connector_id) DO UPDATE SET
                label=excluded.label, connector_type=excluded.connector_type,
                provider_type=excluded.provider_type, version=excluded.version,
                admission_verdict=excluded.admission_verdict,
                registration_type=excluded.registration_type,
                constitution_json=excluded.constitution_json,
                policy_json=excluded.policy_json,
                resource_kinds_json=excluded.resource_kinds_json,
                guide_cards_json=excluded.guide_cards_json,
                updated_at=excluded.updated_at
            """,
            (
                connector.connector_id,
                connector.label,
                connector.connector_type,
                connector.provider_type,
                connector.version,
                connector.admission_verdict,
                connector.registration_type,
                json.dumps(connector.constitution, sort_keys=True),
                json.dumps(connector.policy_declarations, sort_keys=True),
                json.dumps(connector.resource_kinds, sort_keys=True),
                json.dumps(connector.guide_cards, sort_keys=True),
                connector.created_at,
                connector.updated_at,
            ),
        )
        self._db.commit()

    def get_connector(self, connector_id: str) -> ConnectorRecord | None:
        row = self._db.execute(
            "SELECT * FROM connectors WHERE connector_id = ?", (connector_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_connector(row)

    def list_connectors(self, *, connector_type: str | None = None) -> list[ConnectorRecord]:
        if connector_type is not None:
            rows = self._db.execute(
                "SELECT * FROM connectors WHERE connector_type = ?", (connector_type,)
            ).fetchall()
        else:
            rows = self._db.execute("SELECT * FROM connectors").fetchall()
        return [self._row_to_connector(r) for r in rows]

    def delete_connector(self, connector_id: str) -> None:
        self._db.execute("DELETE FROM connectors WHERE connector_id = ?", (connector_id,))
        self._db.commit()

    def connector_exists(self, connector_id: str) -> bool:
        row = self._db.execute(
            "SELECT 1 FROM connectors WHERE connector_id = ?", (connector_id,)
        ).fetchone()
        return row is not None

    # ── Capability CRUD ─────────────────────────────────────────────────

    def upsert_capability(self, capability: CapabilityRecord) -> None:
        self._db.execute(
            """
            INSERT INTO capabilities (capability_name, connector_id, invocation_mode,
                action_name, effect, resource_kind, description, required_inputs_json,
                optional_inputs_json, output_schema_ref, safety_band_min, risk_class,
                idempotency, compensation_capability, record_type, created_at,
                contract_json, synthetic)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(capability_name) DO UPDATE SET
                connector_id=excluded.connector_id, invocation_mode=excluded.invocation_mode,
                action_name=excluded.action_name, effect=excluded.effect,
                resource_kind=excluded.resource_kind, description=excluded.description,
                required_inputs_json=excluded.required_inputs_json,
                optional_inputs_json=excluded.optional_inputs_json,
                output_schema_ref=excluded.output_schema_ref,
                safety_band_min=excluded.safety_band_min, risk_class=excluded.risk_class,
                idempotency=excluded.idempotency,
                compensation_capability=excluded.compensation_capability,
                record_type=excluded.record_type, created_at=excluded.created_at,
                contract_json=excluded.contract_json, synthetic=excluded.synthetic
            """,
            (
                capability.capability_name,
                capability.connector_id,
                capability.invocation_mode,
                capability.action_name,
                capability.effect,
                capability.resource_kind,
                capability.description,
                json.dumps(capability.required_inputs, sort_keys=True),
                json.dumps(capability.optional_inputs, sort_keys=True),
                capability.output_schema_ref,
                capability.safety_band_min,
                capability.risk_class,
                capability.idempotency,
                capability.compensation_capability,
                capability.record_type,
                capability.created_at,
                json.dumps(capability.contract_json, sort_keys=True),
                1 if capability.synthetic else 0,
            ),
        )
        # FTS5 content-sync: single upsert → rebuild
        self._db.execute("INSERT INTO capabilities_fts(capabilities_fts) VALUES ('rebuild')")
        self._db.commit()

    def bulk_upsert_capabilities(
        self,
        capabilities: list[CapabilityRecord],
        *,
        chunk_size: int = 25_000,
    ) -> None:
        """Bulk-insert capabilities with chunked FTS5 content-sync.

        Emits 'delete-all' first, chunk-inserts at *chunk_size* rows,
        then calls ``rebuild_fts_index()`` once at the end.
        """
        self._db.execute("INSERT INTO capabilities_fts(capabilities_fts) VALUES ('delete-all')")
        for i in range(0, len(capabilities), chunk_size):
            chunk = capabilities[i : i + chunk_size]
            self._db.executemany(
                """
                INSERT OR REPLACE INTO capabilities (capability_name, connector_id,
                    invocation_mode, action_name, effect, resource_kind, description,
                    required_inputs_json, optional_inputs_json, output_schema_ref,
                    safety_band_min, risk_class, idempotency, compensation_capability,
                    record_type, created_at, contract_json, synthetic)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                [
                    (
                        c.capability_name,
                        c.connector_id,
                        c.invocation_mode,
                        c.action_name,
                        c.effect,
                        c.resource_kind,
                        c.description,
                        json.dumps(c.required_inputs, sort_keys=True),
                        json.dumps(c.optional_inputs, sort_keys=True),
                        c.output_schema_ref,
                        c.safety_band_min,
                        c.risk_class,
                        c.idempotency,
                        c.compensation_capability,
                        c.record_type,
                        c.created_at,
                        json.dumps(c.contract_json, sort_keys=True),
                        1 if c.synthetic else 0,
                    )
                    for c in chunk
                ],
            )
        self.rebuild_fts_index()

    def get_capability(self, capability_name: str) -> CapabilityRecord | None:
        row = self._db.execute(
            "SELECT * FROM capabilities WHERE capability_name = ?",
            (capability_name,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_capability(row)

    def get_capabilities_by_connector(self, connector_id: str) -> list[CapabilityRecord]:
        rows = self._db.execute(
            "SELECT * FROM capabilities WHERE connector_id = ?", (connector_id,)
        ).fetchall()
        return [self._row_to_capability(r) for r in rows]

    def delete_capability(self, capability_name: str) -> None:
        self._db.execute("DELETE FROM capabilities WHERE capability_name = ?", (capability_name,))
        self._db.execute("INSERT INTO capabilities_fts(capabilities_fts) VALUES ('rebuild')")
        self._db.commit()

    def capability_exists(self, capability_name: str) -> bool:
        row = self._db.execute(
            "SELECT 1 FROM capabilities WHERE capability_name = ?",
            (capability_name,),
        ).fetchone()
        return row is not None

    def count_capabilities(self) -> int:
        row = self._db.execute("SELECT COUNT(*) FROM capabilities").fetchone()
        return int(row[0]) if row else 0

    # ── FTS5 Search ─────────────────────────────────────────────────────

    @staticmethod
    def _sanitize_fts_query(query: str) -> str:
        """Minimal FTS5 query sanitization.

        Strips characters that can cause FTS5 syntax errors while
        preserving meaningful search terms.  Double-quotes phrase
        queries and ``*`` wildcards are preserved.
        """
        if not query:
            return ""
        # Remove characters that break FTS5 MATCH syntax
        unsafe = set("^~!@#$%&/()=?`'{}[]\\|<>.,;:\n\r\t")
        cleaned = "".join(c if c not in unsafe else " " for c in query)
        # Collapse whitespace
        return " ".join(cleaned.split())

    def search_capabilities(
        self,
        query: str,
        *,
        top_k: int = 20,
        connector_ids: list[str] | None = None,
    ) -> list[CapabilityRecord]:
        query = self._sanitize_fts_query(query)
        if not query:
            return []
        if connector_ids:
            placeholders = ",".join("?" for _ in connector_ids)
            rows = self._db.execute(
                f"""
                SELECT c.* FROM capabilities c
                JOIN capabilities_fts fts ON c.rowid = fts.rowid
                WHERE capabilities_fts MATCH ?
                  AND c.connector_id IN ({placeholders})
                ORDER BY rank
                LIMIT ?
                """,
                [query] + connector_ids + [top_k],
            ).fetchall()
        else:
            rows = self._db.execute(
                """
                SELECT c.* FROM capabilities c
                JOIN capabilities_fts fts ON c.rowid = fts.rowid
                WHERE capabilities_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (query, top_k),
            ).fetchall()
        return [self._row_to_capability(r) for r in rows]

    def search_capabilities_by_domain(
        self,
        query: str,
        domains: list[str],
        *,
        top_k: int = 20,
    ) -> list[CapabilityRecord]:
        query = self._sanitize_fts_query(query)
        if not query or not domains:
            return self.search_capabilities(query, top_k=top_k)
        # domain → connector_id prefix: "family.%", "enterprise.%", etc.
        domain_prefixes = [f"{d}.%" for d in domains]
        clauses = " OR ".join("c.connector_id LIKE ?" for _ in domain_prefixes)
        rows = self._db.execute(
            f"""
            SELECT c.* FROM capabilities c
            JOIN capabilities_fts fts ON c.rowid = fts.rowid
            WHERE capabilities_fts MATCH ?
              AND ({clauses})
            ORDER BY rank
            LIMIT ?
            """,
            [query] + domain_prefixes + [top_k],
        ).fetchall()
        return [self._row_to_capability(r) for r in rows]

    def rebuild_fts_index(self) -> None:
        self._db.execute("INSERT INTO capabilities_fts(capabilities_fts) VALUES ('rebuild')")
        self._db.commit()

    def find_capabilities(
        self,
        *,
        resource_kind: str,
        invocation_mode: str,
        effect: str,
        connector_id: str | None = None,
        safety_band: str = "RED",
        record_type: str | None = None,
    ) -> list[CapabilityRecord]:
        """Structured capability lookup backed by ``idx_capability_lookup``.

        Returns capabilities matching ``resource_kind`` + ``invocation_mode`` +
        ``effect`` (and optionally ``connector_id`` / ``record_type``) whose
        ``safety_band_min`` is at or below ``safety_band`` (the actor's maximum
        band).  ``safety_band='RED'`` admits every band.

        This is the exact-match (Pass 2) query for ``CapabilityBinderService``.
        """
        rank = {"GREEN": 1, "AMBER": 2, "RED": 3}
        max_rank = rank.get(safety_band, 3)
        allowed_bands = [b for b, r in rank.items() if r <= max_rank]
        band_placeholders = ",".join("?" for _ in allowed_bands)

        sql = [
            "SELECT * FROM capabilities",
            "WHERE resource_kind = ? AND invocation_mode = ? AND effect = ?",
            f"AND safety_band_min IN ({band_placeholders})",
        ]
        params: list[Any] = [resource_kind, invocation_mode, effect, *allowed_bands]
        if connector_id is not None:
            sql.append("AND connector_id = ?")
            params.append(connector_id)
        if record_type is not None:
            sql.append("AND record_type = ?")
            params.append(record_type)

        rows = self._db.execute(" ".join(sql), params).fetchall()
        return [self._row_to_capability(r) for r in rows]

    # ── Resource Kinds ──────────────────────────────────────────────────

    def upsert_resource_kind(self, kind: ResourceKindRecord) -> None:
        self._db.execute(
            """
            INSERT INTO resource_kinds (kind_id, connector_id, label, schema_json,
                verifier_affordances_json, created_at)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(kind_id) DO UPDATE SET
                connector_id=excluded.connector_id, label=excluded.label,
                schema_json=excluded.schema_json,
                verifier_affordances_json=excluded.verifier_affordances_json
            """,
            (
                kind.kind_id,
                kind.connector_id,
                kind.label,
                json.dumps(kind.schema, sort_keys=True),
                json.dumps(kind.verifier_affordances, sort_keys=True),
                kind.created_at,
            ),
        )
        self._db.commit()

    def get_resource_kinds_by_connector(self, connector_id: str) -> list[ResourceKindRecord]:
        rows = self._db.execute(
            "SELECT * FROM resource_kinds WHERE connector_id = ?", (connector_id,)
        ).fetchall()
        return [self._row_to_resource_kind(r) for r in rows]

    def get_resource_kind(self, kind_id: str) -> ResourceKindRecord | None:
        row = self._db.execute(
            "SELECT * FROM resource_kinds WHERE kind_id = ?", (kind_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_resource_kind(row)

    # ── Constitutions ───────────────────────────────────────────────────

    def upsert_constitution(self, constitution: ConstitutionRecord) -> None:
        self._db.execute(
            """
            INSERT INTO connector_constitutions (connector_id, constitution_id,
                schema_version, authored_by, authored_at, last_proven_at,
                execution_phases_json, prerequisite_reads_json,
                conflict_analysis_rules_json, hil_gates_json,
                mutation_sequencing_json, verification_requirements_json,
                companion_resource_roles_json, precondition_summary,
                companion_resource_summary, hil_trigger_summary, degradation_policy)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(connector_id) DO UPDATE SET
                constitution_id=excluded.constitution_id,
                schema_version=excluded.schema_version,
                authored_by=excluded.authored_by,
                authored_at=excluded.authored_at,
                last_proven_at=excluded.last_proven_at,
                execution_phases_json=excluded.execution_phases_json,
                prerequisite_reads_json=excluded.prerequisite_reads_json,
                conflict_analysis_rules_json=excluded.conflict_analysis_rules_json,
                hil_gates_json=excluded.hil_gates_json,
                mutation_sequencing_json=excluded.mutation_sequencing_json,
                verification_requirements_json=excluded.verification_requirements_json,
                companion_resource_roles_json=excluded.companion_resource_roles_json,
                precondition_summary=excluded.precondition_summary,
                companion_resource_summary=excluded.companion_resource_summary,
                hil_trigger_summary=excluded.hil_trigger_summary,
                degradation_policy=excluded.degradation_policy
            """,
            (
                constitution.connector_id,
                constitution.constitution_id,
                constitution.schema_version,
                constitution.authored_by,
                constitution.authored_at,
                constitution.last_proven_at,
                json.dumps(constitution.execution_phases, sort_keys=True),
                json.dumps(constitution.prerequisite_reads, sort_keys=True),
                json.dumps(constitution.conflict_analysis_rules, sort_keys=True),
                json.dumps(constitution.hil_gates, sort_keys=True),
                json.dumps(constitution.mutation_sequencing, sort_keys=True),
                json.dumps(constitution.verification_requirements, sort_keys=True),
                json.dumps(constitution.companion_resource_roles, sort_keys=True),
                constitution.precondition_summary,
                constitution.companion_resource_summary,
                constitution.hil_trigger_summary,
                constitution.degradation_policy,
            ),
        )
        self._db.commit()

    def get_constitution(self, connector_id: str) -> ConstitutionRecord | None:
        row = self._db.execute(
            "SELECT * FROM connector_constitutions WHERE connector_id = ?",
            (connector_id,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_constitution(row)

    def list_constitutions(self) -> list[ConstitutionRecord]:
        rows = self._db.execute("SELECT * FROM connector_constitutions").fetchall()
        return [self._row_to_constitution(r) for r in rows]

    # ── Bulk ────────────────────────────────────────────────────────────

    def load_from_manifest_batch(self, batch: CapabilityRegistrationBatch) -> LoadResult:
        """Atomic batch load: entire connector batch is admitted or none of it.

        Uses a single transaction so partial failure rolls back the
        connector and all capabilities.  Inserts are done raw (not via
        the public commit()-ing methods) so the transaction boundary
        is preserved.  FTS5 is rebuilt exactly once at the end.
        """
        try:
            self._db.execute("BEGIN IMMEDIATE")
            # --- connector ---
            self._db.execute(
                """
                INSERT INTO connectors (connector_id, label, connector_type, provider_type,
                    version, admission_verdict, registration_type, constitution_json,
                    policy_json, resource_kinds_json, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(connector_id) DO UPDATE SET
                    label=excluded.label, connector_type=excluded.connector_type,
                    provider_type=excluded.provider_type, version=excluded.version,
                    admission_verdict=excluded.admission_verdict,
                    registration_type=excluded.registration_type,
                    constitution_json=excluded.constitution_json,
                    policy_json=excluded.policy_json,
                    resource_kinds_json=excluded.resource_kinds_json,
                    updated_at=excluded.updated_at
                """,
                (
                    batch.connector.connector_id,
                    batch.connector.label,
                    batch.connector.connector_type,
                    batch.connector.provider_type,
                    batch.connector.version,
                    batch.connector.admission_verdict,
                    batch.connector.registration_type,
                    json.dumps(batch.connector.constitution, sort_keys=True),
                    json.dumps(batch.connector.policy_declarations, sort_keys=True),
                    json.dumps(batch.connector.resource_kinds, sort_keys=True),
                    batch.connector.created_at,
                    batch.connector.updated_at,
                ),
            )
            # --- capabilities (chunked insert, no per-row FTS rebuild) ---
            chunk_size = 25_000
            for i in range(0, len(batch.capabilities), chunk_size):
                chunk = batch.capabilities[i : i + chunk_size]
                self._db.executemany(
                    """
                    INSERT OR REPLACE INTO capabilities (capability_name, connector_id,
                        invocation_mode, action_name, effect, resource_kind, description,
                        required_inputs_json, optional_inputs_json, output_schema_ref,
                        safety_band_min, risk_class, idempotency, compensation_capability,
                        record_type, created_at, contract_json, synthetic)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    [
                        (
                            c.capability_name,
                            c.connector_id,
                            c.invocation_mode,
                            c.action_name,
                            c.effect,
                            c.resource_kind,
                            c.description,
                            json.dumps(c.required_inputs, sort_keys=True),
                            json.dumps(c.optional_inputs, sort_keys=True),
                            c.output_schema_ref,
                            c.safety_band_min,
                            c.risk_class,
                            c.idempotency,
                            c.compensation_capability,
                            c.record_type,
                            c.created_at,
                            json.dumps(c.contract_json, sort_keys=True),
                            1 if c.synthetic else 0,
                        )
                        for c in chunk
                    ],
                )
            # --- resource kinds ---
            for rk in batch.resource_kinds:
                self._db.execute(
                    """
                    INSERT INTO resource_kinds (kind_id, connector_id, label, schema_json,
                        verifier_affordances_json, created_at)
                    VALUES (?,?,?,?,?,?)
                    ON CONFLICT(kind_id) DO UPDATE SET
                        connector_id=excluded.connector_id, label=excluded.label,
                        schema_json=excluded.schema_json,
                        verifier_affordances_json=excluded.verifier_affordances_json
                    """,
                    (
                        rk.kind_id,
                        rk.connector_id,
                        rk.label,
                        json.dumps(rk.schema, sort_keys=True),
                        json.dumps(rk.verifier_affordances, sort_keys=True),
                        rk.created_at,
                    ),
                )
            # --- constitution ---
            if batch.constitution is not None:
                c = batch.constitution
                self._db.execute(
                    """
                    INSERT INTO connector_constitutions (connector_id, constitution_id,
                        schema_version, authored_by, authored_at, last_proven_at,
                        execution_phases_json, prerequisite_reads_json,
                        conflict_analysis_rules_json, hil_gates_json,
                        mutation_sequencing_json, verification_requirements_json,
                        companion_resource_roles_json, precondition_summary,
                        companion_resource_summary, hil_trigger_summary, degradation_policy)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(connector_id) DO UPDATE SET
                        constitution_id=excluded.constitution_id,
                        schema_version=excluded.schema_version,
                        authored_by=excluded.authored_by,
                        authored_at=excluded.authored_at,
                        last_proven_at=excluded.last_proven_at,
                        execution_phases_json=excluded.execution_phases_json,
                        prerequisite_reads_json=excluded.prerequisite_reads_json,
                        conflict_analysis_rules_json=excluded.conflict_analysis_rules_json,
                        hil_gates_json=excluded.hil_gates_json,
                        mutation_sequencing_json=excluded.mutation_sequencing_json,
                        verification_requirements_json=excluded.verification_requirements_json,
                        companion_resource_roles_json=excluded.companion_resource_roles_json,
                        precondition_summary=excluded.precondition_summary,
                        companion_resource_summary=excluded.companion_resource_summary,
                        hil_trigger_summary=excluded.hil_trigger_summary,
                        degradation_policy=excluded.degradation_policy
                    """,
                    (
                        c.connector_id,
                        c.constitution_id,
                        c.schema_version,
                        c.authored_by,
                        c.authored_at,
                        c.last_proven_at,
                        json.dumps(c.execution_phases, sort_keys=True),
                        json.dumps(c.prerequisite_reads, sort_keys=True),
                        json.dumps(c.conflict_analysis_rules, sort_keys=True),
                        json.dumps(c.hil_gates, sort_keys=True),
                        json.dumps(c.mutation_sequencing, sort_keys=True),
                        json.dumps(c.verification_requirements, sort_keys=True),
                        json.dumps(c.companion_resource_roles, sort_keys=True),
                        c.precondition_summary,
                        c.companion_resource_summary,
                        c.hil_trigger_summary,
                        c.degradation_policy,
                    ),
                )
            self._db.execute("COMMIT")
            # Rebuild FTS5 once after the transaction commits
            self.rebuild_fts_index()
            return LoadResult(
                total_connectors=1,
                total_capabilities=len(batch.capabilities),
                admitted=len(batch.capabilities),
                rejected=0,
                errors=[],
            )
        except Exception as exc:
            try:
                self._db.execute("ROLLBACK")
            except Exception:
                pass
            return LoadResult(
                total_connectors=1,
                total_capabilities=len(batch.capabilities),
                admitted=0,
                rejected=len(batch.capabilities),
                errors=[f"batch load failed, rolled back: {exc}"],
            )

    # ── Graph ontology queries (for CapabilityTypeResolver) ────────────

    def resolve_concept(self, alias: str, domain: str = "") -> list[dict[str, Any]]:
        if domain:
            rows = self._db.execute(
                """
                SELECT alias, canonical_concept, domain, weight, generic, source
                FROM concept_aliases WHERE alias = ? AND (domain = ? OR domain IS NULL OR domain = '')
                ORDER BY weight DESC
                """,
                (alias, domain),
            ).fetchall()
        else:
            rows = self._db.execute(
                """
                SELECT alias, canonical_concept, domain, weight, generic, source
                FROM concept_aliases WHERE alias = ?
                ORDER BY weight DESC
                """,
                (alias,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_concept_resource_family(self, concept: str, domain: str = "") -> list[dict[str, Any]]:
        if domain:
            rows = self._db.execute(
                """
                SELECT concept, resource_family, domain, weight
                FROM concept_resource_edges WHERE concept = ? AND domain = ?
                ORDER BY weight DESC
                """,
                (concept, domain),
            ).fetchall()
        else:
            rows = self._db.execute(
                """
                SELECT concept, resource_family, domain, weight
                FROM concept_resource_edges WHERE concept = ?
                ORDER BY weight DESC
                """,
                (concept,),
            ).fetchall()
        return [dict(r) for r in rows]

    def resolve_operation(self, alias: str, effect: str = "") -> list[dict[str, Any]]:
        if effect:
            rows = self._db.execute(
                """
                SELECT alias, operation_family, effect, weight, generic
                FROM operation_aliases WHERE alias = ? AND effect = ?
                ORDER BY weight DESC
                """,
                (alias, effect),
            ).fetchall()
        else:
            rows = self._db.execute(
                """
                SELECT alias, operation_family, effect, weight, generic
                FROM operation_aliases WHERE alias = ?
                ORDER BY weight DESC
                """,
                (alias,),
            ).fetchall()
        return [dict(r) for r in rows]

    def lookup_capability_by_type(
        self,
        domain: str,
        resource_family: str,
        operation_family: str,
        effect: str,
    ) -> list[dict[str, Any]]:
        rows = self._db.execute(
            """
            SELECT capability_name, connector_id, domain, resource_family,
                   operation_family, effect, side_effect_class, risk_class
            FROM capability_type_index
            WHERE domain = ? AND resource_family = ? AND operation_family = ? AND effect = ?
            """,
            (domain, resource_family, operation_family, effect),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Graph ontology upserts ─────────────────────────────────────────

    def upsert_concept_alias(
        self,
        alias: str,
        canonical_concept: str,
        domain: str = "",
        weight: float = 1.0,
        generic: bool = False,
        source: str = "catalog",
    ) -> None:
        self._db.execute(
            """
            INSERT OR REPLACE INTO concept_aliases (alias, canonical_concept, domain, weight, generic, source)
            VALUES (?,?,?,?,?,?)
            """,
            (alias, canonical_concept, domain, weight, 1 if generic else 0, source),
        )
        self._db.commit()

    def upsert_concept_resource_edge(
        self,
        concept: str,
        resource_family: str,
        domain: str,
        weight: float = 1.0,
    ) -> None:
        self._db.execute(
            """
            INSERT OR REPLACE INTO concept_resource_edges (concept, resource_family, domain, weight)
            VALUES (?,?,?,?)
            """,
            (concept, resource_family, domain, weight),
        )
        self._db.commit()

    def upsert_resource_connector_edge(
        self,
        domain: str,
        resource_family: str,
        connector_id: str,
        weight: float = 1.0,
        role: str = "primary",
    ) -> None:
        self._db.execute(
            """
            INSERT OR REPLACE INTO resource_connector_edges (domain, resource_family, connector_id, weight, role)
            VALUES (?,?,?,?,?)
            """,
            (domain, resource_family, connector_id, weight, role),
        )
        self._db.commit()

    def upsert_operation_alias(
        self,
        alias: str,
        operation_family: str,
        effect: str,
        weight: float = 1.0,
        generic: bool = True,
    ) -> None:
        self._db.execute(
            """
            INSERT OR REPLACE INTO operation_aliases (alias, operation_family, effect, weight, generic)
            VALUES (?,?,?,?,?)
            """,
            (alias, operation_family, effect, weight, 1 if generic else 0),
        )
        self._db.commit()

    def upsert_operation_equivalence(
        self,
        canonical_operation: str,
        equivalent_operation: str,
        resource_family: str | None = None,
        domain: str | None = None,
    ) -> None:
        self._db.execute(
            """
            INSERT OR REPLACE INTO operation_equivalences (canonical_operation, equivalent_operation, resource_family, domain)
            VALUES (?,?,?,?)
            """,
            (canonical_operation, equivalent_operation, resource_family or "", domain or ""),
        )
        self._db.commit()

    def get_operation_equivalences(
        self, canonical_operation: str | None = None
    ) -> list[dict[str, Any]]:
        if canonical_operation is not None:
            rows = self._db.execute(
                """
                SELECT canonical_operation, equivalent_operation, resource_family, domain
                FROM operation_equivalences WHERE canonical_operation = ?
                """,
                (canonical_operation,),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT canonical_operation, equivalent_operation, resource_family, domain FROM operation_equivalences"
            ).fetchall()
        return [dict(r) for r in rows]

    def upsert_capability_type_index(
        self,
        capability_name: str,
        connector_id: str,
        domain: str,
        resource_family: str,
        operation_family: str,
        effect: str,
        side_effect_class: str | None = None,
        risk_class: str | None = None,
    ) -> None:
        self._db.execute(
            """
            INSERT OR REPLACE INTO capability_type_index (capability_name, connector_id, domain,
                resource_family, operation_family, effect, side_effect_class, risk_class)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            (
                capability_name,
                connector_id,
                domain,
                resource_family,
                operation_family,
                effect,
                side_effect_class,
                risk_class,
            ),
        )
        self._db.commit()

    # ── Row deserialisation helpers ─────────────────────────────────────

    def _row_to_connector(self, row: sqlite3.Row) -> ConnectorRecord:
        return ConnectorRecord(
            connector_id=row["connector_id"],
            label=row["label"],
            connector_type=row["connector_type"],
            provider_type=row["provider_type"],
            version=row["version"],
            admission_verdict=row["admission_verdict"],
            registration_type=row["registration_type"],
            constitution=json.loads(row["constitution_json"]),
            policy_declarations=json.loads(row["policy_json"]),
            resource_kinds=json.loads(row["resource_kinds_json"]),
            guide_cards=json.loads(
                row["guide_cards_json"] if "guide_cards_json" in row.keys() else "[]"
            ),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _row_to_capability(self, row: sqlite3.Row) -> CapabilityRecord:
        return CapabilityRecord(
            capability_name=row["capability_name"],
            connector_id=row["connector_id"],
            invocation_mode=row["invocation_mode"],
            action_name=row["action_name"],
            effect=row["effect"],
            resource_kind=row["resource_kind"],
            description=row["description"],
            required_inputs=json.loads(row["required_inputs_json"]),
            optional_inputs=json.loads(row["optional_inputs_json"]),
            output_schema_ref=row["output_schema_ref"],
            safety_band_min=row["safety_band_min"],
            risk_class=row["risk_class"],
            idempotency=row["idempotency"],
            compensation_capability=row["compensation_capability"],
            record_type=row["record_type"],
            created_at=row["created_at"],
            contract_json=json.loads(row["contract_json"]),
            synthetic=bool(row["synthetic"]),
        )

    def _row_to_resource_kind(self, row: sqlite3.Row) -> ResourceKindRecord:
        return ResourceKindRecord(
            kind_id=row["kind_id"],
            connector_id=row["connector_id"],
            label=row["label"],
            schema=json.loads(row["schema_json"]),
            verifier_affordances=json.loads(row["verifier_affordances_json"]),
            created_at=row["created_at"],
        )

    def _row_to_constitution(self, row: sqlite3.Row) -> ConstitutionRecord:
        return ConstitutionRecord(
            connector_id=row["connector_id"],
            constitution_id=row["constitution_id"],
            schema_version=row["schema_version"],
            authored_by=row["authored_by"],
            authored_at=row["authored_at"],
            last_proven_at=row["last_proven_at"],
            execution_phases=json.loads(row["execution_phases_json"]),
            prerequisite_reads=json.loads(row["prerequisite_reads_json"]),
            conflict_analysis_rules=json.loads(row["conflict_analysis_rules_json"]),
            hil_gates=json.loads(row["hil_gates_json"]),
            mutation_sequencing=json.loads(row["mutation_sequencing_json"]),
            verification_requirements=json.loads(row["verification_requirements_json"]),
            companion_resource_roles=json.loads(row["companion_resource_roles_json"]),
            precondition_summary=row["precondition_summary"],
            companion_resource_summary=row["companion_resource_summary"],
            hil_trigger_summary=row["hil_trigger_summary"],
            degradation_policy=row["degradation_policy"],
        )
