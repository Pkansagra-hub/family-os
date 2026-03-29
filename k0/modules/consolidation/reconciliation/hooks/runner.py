"""PostReconciliationHookRunner -- post-R7 content-generation coordinator (M9.6).

Runs AFTER R7 commits StagedWrites, BEFORE R8 bus events.
Hook failures are logged but do NOT roll back R7 writes.

Execution order per record:
    1. regenerate_summary (produces new embedding_text)
    2. recompute_centroid (uses embedding_text for inline vector)
    3. Single batched UPDATE to write all hook outputs
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from k0.modules.consolidation.reconciliation.hooks import (
    HOOK_RECOMPUTE_CENTROID,
    HOOK_REGENERATE_SUMMARY,
)
from k0.modules.consolidation.reconciliation.hooks.centroid_recompute import CentroidRecomputer
from k0.modules.consolidation.reconciliation.hooks.result import HookResult
from k0.modules.consolidation.reconciliation.hooks.summary_regen import SummaryRegenerator
from k0.modules.consolidation.reconciliation.result import ReconciliationResult
from k0.pipelines.p03.staged_writes import StagedWrite

logger = logging.getLogger(__name__)


@dataclass
class HookBatchResult:
    """Result of running hooks for an entire batch."""

    total: int = 0
    summary_regen_count: int = 0
    centroid_recompute_count: int = 0
    skipped: int = 0
    failed: int = 0
    total_time_ms: float = 0.0
    per_record: list[HookResult] = field(default_factory=list)


# -- DB writer protocol --


class HookDBWriterLike:
    """Writes hook outputs to the database. One UPDATE per record."""

    async def write_hook_outputs(
        self,
        layer: str,
        record_id: str,
        pk_column: str,
        summary_json: str | None,
        embedding_text: str | None,
        embedding_vector: bytes | None,
        embedding_model: str | None,
        source_texts_json: str | None,
    ) -> None:
        """Write all hook outputs in a single UPDATE."""
        ...


class DefaultHookDBWriter(HookDBWriterLike):
    """Writes hook outputs via asyncpg connection."""

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    async def write_hook_outputs(
        self,
        layer: str,
        record_id: str,
        pk_column: str,
        summary_json: str | None,
        embedding_text: str | None,
        embedding_vector: bytes | None,
        embedding_model: str | None,
        source_texts_json: str | None,
    ) -> None:
        set_parts: list[str] = []
        params: list[Any] = []
        idx = 1

        if summary_json is not None and layer == "st_epi":
            idx += 1
            set_parts.append(f"episode_summary = ${idx}")
            params.append(summary_json)

        if embedding_text is not None:
            idx += 1
            set_parts.append(f"embedding_text = ${idx}")
            params.append(embedding_text)

        if embedding_vector is not None:
            idx += 1
            set_parts.append(f"embedding_vector = ${idx}")
            params.append(embedding_vector)

        if embedding_model is not None:
            idx += 1
            set_parts.append(f"embedding_model = ${idx}")
            params.append(embedding_model)

        if source_texts_json is not None:
            idx += 1
            set_parts.append(f"source_texts_json = ${idx}")
            params.append(source_texts_json)

        if not set_parts:
            return

        idx += 1
        set_parts.append(f"updated_at = ${idx}")
        params.append(int(time.time() * 1000))

        set_clause = ", ".join(set_parts)
        sql = (
            f"UPDATE {layer} SET {set_clause} "  # noqa: S608
            f"WHERE {pk_column} = $1 AND archival_status = 'ACTIVE'"
        )
        await self._conn.execute(sql, record_id, *params)


# -- Main class --


class PostReconciliationHookRunner:
    """Post-R7 coordinator that executes content-generation hooks.

    Runs AFTER R7 commits StagedWrites, BEFORE R8 bus events.
    Hook failures are logged but do NOT roll back R7 writes.
    """

    def __init__(
        self,
        summary_regen: SummaryRegenerator | None = None,
        centroid_recomputer: CentroidRecomputer | None = None,
        db_writer: HookDBWriterLike | None = None,
        registry: Any = None,
        conn: Any = None,
    ) -> None:
        self._summary = summary_regen or SummaryRegenerator()
        self._centroid = centroid_recomputer or CentroidRecomputer()
        self._db_writer = db_writer or (DefaultHookDBWriter(conn) if conn else None)
        self._registry = registry
        self._conn = conn

    async def run(
        self,
        hook_inputs: list[tuple[ReconciliationResult, StagedWrite]],
    ) -> HookBatchResult:
        """Execute hooks for a batch of reconciliation results.

        Args:
            hook_inputs: (result, staged_write) pairs from R6.
                         Only pairs with non-empty hooks_required are processed.

        Returns:
            HookBatchResult with per-record and aggregate results.
        """
        start = time.monotonic()
        result = HookBatchResult(total=len(hook_inputs))

        for rec_result, write in hook_inputs:
            if not rec_result.hooks_required:
                result.skipped += 1
                continue

            record_id = rec_result.match_id or write.record_id
            layer = rec_result.layer

            try:
                hook_result = await self._run_hooks_for_record(rec_result, write, record_id)
                result.per_record.append(hook_result)
                if hook_result.summary_regenerated:
                    result.summary_regen_count += 1
                if hook_result.centroid_recomputed:
                    result.centroid_recompute_count += 1
            except Exception as exc:
                logger.error(
                    "Hook execution failed for %s/%s: %s",
                    layer,
                    record_id,
                    exc,
                )
                result.failed += 1
                result.per_record.append(HookResult.failure(layer, record_id, str(exc)))

        result.total_time_ms = (time.monotonic() - start) * 1000
        return result

    async def _run_hooks_for_record(
        self,
        rec_result: ReconciliationResult,
        write: StagedWrite,
        record_id: str,
    ) -> HookResult:
        """Execute hooks for a single record in correct order."""
        rec_start = time.monotonic()

        layer = rec_result.layer
        hooks = rec_result.hooks_required
        new_embedding_text: str | None = None
        new_summary_json: str | None = None
        new_embedding_vector: bytes | None = None
        new_embedding_model: str | None = None
        new_source_texts_json: str | None = None

        did_summary = False
        did_centroid = False

        # Hook 1: regenerate_summary (must run first -- produces new embedding_text)
        if HOOK_REGENERATE_SUMMARY in hooks:
            regen = await self._summary.regenerate(
                layer=layer,
                record_id=record_id,
                spec=self._get_spec(layer),
                source_event_ids=list(write.source_event_ids),
                record_data=write.record_data,
                conn=self._conn,
            )
            new_embedding_text = regen.embedding_text
            new_summary_json = regen.summary_json
            new_embedding_model = regen.embedding_model
            new_source_texts_json = regen.source_texts_json
            did_summary = True

        # Hook 2: recompute_centroid (uses new embedding_text if available)
        if HOOK_RECOMPUTE_CENTROID in hooks:
            centroid = await self._centroid.recompute(
                layer=layer,
                record_id=record_id,
                spec=self._get_spec(layer),
                source_event_ids=list(write.source_event_ids),
                embedding_text=new_embedding_text,
                conn=self._conn,
            )
            if centroid.embedding_vector is not None:
                new_embedding_vector = centroid.embedding_vector
                new_embedding_model = centroid.embedding_model or new_embedding_model
                did_centroid = True

        # Batched UPDATE: write all hook outputs in one statement
        if self._db_writer is not None:
            pk_col = self._get_pk_column(layer)
            await self._db_writer.write_hook_outputs(
                layer=layer,
                record_id=record_id,
                pk_column=pk_col,
                summary_json=new_summary_json,
                embedding_text=new_embedding_text,
                embedding_vector=new_embedding_vector,
                embedding_model=new_embedding_model,
                source_texts_json=new_source_texts_json,
            )

        elapsed_ms = (time.monotonic() - rec_start) * 1000
        return HookResult.success(
            layer=layer,
            record_id=record_id,
            summary=did_summary,
            centroid=did_centroid,
            time_ms=elapsed_ms,
        )

    def _get_spec(self, layer: str) -> Any:
        if self._registry is not None:
            return self._registry.get(layer)
        return None

    def _get_pk_column(self, layer: str) -> str:
        spec = self._get_spec(layer)
        if spec is not None:
            return spec.pk_column
        # Fallback mapping
        _PK_MAP = {
            "st_epi": "episode_id",
            "st_sem": "pattern_id",
            "st_procedural": "routine_id",
            "st_social": "relationship_id",
            "st_prospective": "intention_id",
            "st_kg_dom": "entity_id",
            "st_kg_edges": "edge_id",
        }
        return _PK_MAP.get(layer, "id")
