"""
RelatedContextFetcher - GAP-001 Milestone 5 (Issue 5.3)

Fetches related truth records across all layers for given entities.
Returns structured context for LLM consumption.

GAP Reference: GAP_001 Section 6 (Rich LLM Context)
Spec Reference: D:\\familyos\\docs\\plans\\GAP_001_MILESTONE_5_CONTEXT_EXPANDER.md
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class RelatedContext:
    """
    Structured context from related records.

    Contains records from all truth layers that are related
    to the expanded entity set.

    Attributes:
        episodes: Related episodic memories
        patterns: Semantic patterns for actors
        routines: Procedural routines
        relationships: Social relationships
        intentions: Active intentions/goals
        entities: Entity definitions from st_kg_dom
    """

    episodes: List[Dict] = field(default_factory=list)
    patterns: List[Dict] = field(default_factory=list)
    routines: List[Dict] = field(default_factory=list)
    relationships: List[Dict] = field(default_factory=list)
    intentions: List[Dict] = field(default_factory=list)
    entities: List[Dict] = field(default_factory=list)

    def to_dict(self) -> Dict:
        """Convert to dictionary for LLM context."""
        return {
            "related_episodes": self.episodes,
            "actor_patterns": self.patterns,
            "routines": self.routines,
            "relationships": self.relationships,
            "active_intentions": self.intentions,
            "related_entities": self.entities,
        }

    @property
    def total_records(self) -> int:
        """Total number of related records."""
        return (
            len(self.episodes)
            + len(self.patterns)
            + len(self.routines)
            + len(self.relationships)
            + len(self.intentions)
            + len(self.entities)
        )

    def summary(self) -> Dict:
        """Summary for logging."""
        return {
            "episodes": len(self.episodes),
            "patterns": len(self.patterns),
            "routines": len(self.routines),
            "relationships": len(self.relationships),
            "intentions": len(self.intentions),
            "entities": len(self.entities),
            "total": self.total_records,
        }


class RelatedContextFetcher:
    """
    Fetches related context for entities from all truth layers.

    Queries each truth layer for records that reference the given
    entities, using the appropriate column for each layer:
    - st_epi: participants_json (JSON array containment)
    - st_sem: actor_id
    - st_procedural: actor_id
    - st_social: actor_a_id OR actor_b_id
    - st_prospective: actor_id

    Usage:
        fetcher = RelatedContextFetcher(max_per_layer=10)
        context = await fetcher.fetch({"Mom", "Dad"}, conn)
        print(context.summary())
    """

    def __init__(
        self,
        max_per_layer: int = 10,
        recency_days: int = 30,
    ):
        """
        Initialize fetcher.

        Args:
            max_per_layer: Maximum records per layer
            recency_days: Filter by recency (0 = no filter)
        """
        self.max_per_layer = max_per_layer
        self.recency_days = recency_days

    async def fetch(
        self,
        entity_ids: Set[str],
        conn: Any,
        tenant_id: Optional[str] = None,
        exclude_record_ids: Optional[Set[str]] = None,
    ) -> RelatedContext:
        """
        Fetch related context for entities.

        Args:
            entity_ids: Entity IDs to search for
            conn: asyncpg database connection
            tenant_id: Optional tenant filter
            exclude_record_ids: IDs to exclude (already in direct matches)

        Returns:
            RelatedContext with records from all layers
        """
        if not entity_ids:
            return RelatedContext()

        entity_list = list(entity_ids)
        exclude = exclude_record_ids or set()

        context = RelatedContext()

        # Fetch from each layer
        context.episodes = await self._fetch_episodes(entity_list, conn, tenant_id, exclude)
        context.patterns = await self._fetch_patterns(entity_list, conn, tenant_id, exclude)
        context.routines = await self._fetch_routines(entity_list, conn, tenant_id, exclude)
        context.relationships = await self._fetch_relationships(
            entity_list, conn, tenant_id, exclude
        )
        context.intentions = await self._fetch_intentions(entity_list, conn, tenant_id, exclude)

        logger.debug(
            "RelatedContextFetcher: fetch complete",
            extra=context.summary(),
        )

        return context

    async def _fetch_episodes(
        self,
        entity_ids: List[str],
        conn: Any,
        tenant_id: Optional[str],
        exclude: Set[str],
    ) -> List[Dict]:
        """Fetch episodes involving these entities."""
        # participants_json is TEXT, so use LIKE patterns for containment
        # Build OR clause for each entity
        entity_patterns = [f'%"{eid}"%' for eid in entity_ids]

        query = """
            SELECT
                episode_id,
                embedding_text,
                start_time_utc,
                end_time_utc,
                participants_json,
                primary_location,
                confidence_score as confidence
            FROM st_epi
            WHERE (archival_status IS NULL OR archival_status = 'ACTIVE')
              AND (
        """

        # Add LIKE clauses for each entity
        like_clauses = [f"participants_json LIKE ${i+1}" for i in range(len(entity_patterns))]
        query += " OR ".join(like_clauses)
        query += ")"

        params: List[Any] = entity_patterns

        if tenant_id:
            query += f" AND tenant_id = ${len(params) + 1}"
            params.append(tenant_id)

        query += f" ORDER BY start_time_utc DESC LIMIT {self.max_per_layer}"

        try:
            rows = await conn.fetch(query, *params)
            return [dict(r) for r in rows if r["episode_id"] not in exclude]
        except Exception as e:
            logger.warning(
                "RelatedContextFetcher: failed to fetch episodes",
                extra={"error": str(e)},
            )
            return []

    async def _fetch_patterns(
        self,
        entity_ids: List[str],
        conn: Any,
        tenant_id: Optional[str],
        exclude: Set[str],
    ) -> List[Dict]:
        """Fetch semantic patterns for these actors."""
        query = """
            SELECT
                pattern_id,
                pattern_type,
                pattern_name,
                embedding_text,
                actor_id,
                observation_count,
                confidence_score as confidence,
                source_texts_json
            FROM st_sem
            WHERE actor_id = ANY($1)
              AND (archival_status IS NULL OR archival_status = 'ACTIVE')
        """
        params: List[Any] = [entity_ids]

        if tenant_id:
            query += " AND tenant_id = $2"
            params.append(tenant_id)

        query += f" ORDER BY observation_count DESC LIMIT {self.max_per_layer}"

        try:
            rows = await conn.fetch(query, *params)
            return [dict(r) for r in rows if r["pattern_id"] not in exclude]
        except Exception as e:
            logger.warning(
                "RelatedContextFetcher: failed to fetch patterns",
                extra={"error": str(e)},
            )
            return []

    async def _fetch_routines(
        self,
        entity_ids: List[str],
        conn: Any,
        tenant_id: Optional[str],
        exclude: Set[str],
    ) -> List[Dict]:
        """Fetch procedural routines for these actors."""
        query = """
            SELECT
                routine_id,
                routine_name,
                embedding_text,
                actor_id,
                observation_count,
                regularity_score
            FROM st_procedural
            WHERE actor_id = ANY($1)
              AND (archival_status IS NULL OR archival_status = 'ACTIVE')
        """
        params: List[Any] = [entity_ids]

        if tenant_id:
            query += " AND tenant_id = $2"
            params.append(tenant_id)

        query += f" ORDER BY observation_count DESC LIMIT {self.max_per_layer}"

        try:
            rows = await conn.fetch(query, *params)
            return [dict(r) for r in rows if r["routine_id"] not in exclude]
        except Exception as e:
            logger.warning(
                "RelatedContextFetcher: failed to fetch routines",
                extra={"error": str(e)},
            )
            return []

    async def _fetch_relationships(
        self,
        entity_ids: List[str],
        conn: Any,
        tenant_id: Optional[str],
        exclude: Set[str],
    ) -> List[Dict]:
        """Fetch social relationships involving these entities."""
        query = """
            SELECT
                relationship_id,
                actor_a_id,
                actor_b_id,
                relationship_type,
                relationship_label,
                embedding_text,
                relationship_strength as strength,
                intimacy_level
            FROM st_social
            WHERE (actor_a_id = ANY($1) OR actor_b_id = ANY($1))
              AND (archival_status IS NULL OR archival_status = 'ACTIVE')
        """
        params: List[Any] = [entity_ids]

        if tenant_id:
            query += " AND tenant_id = $2"
            params.append(tenant_id)

        query += f" ORDER BY relationship_strength DESC LIMIT {self.max_per_layer}"

        try:
            rows = await conn.fetch(query, *params)
            return [dict(r) for r in rows if r["relationship_id"] not in exclude]
        except Exception as e:
            logger.warning(
                "RelatedContextFetcher: failed to fetch relationships",
                extra={"error": str(e)},
            )
            return []

    async def _fetch_intentions(
        self,
        entity_ids: List[str],
        conn: Any,
        tenant_id: Optional[str],
        exclude: Set[str],
    ) -> List[Dict]:
        """Fetch active intentions for these actors."""
        query = """
            SELECT
                intention_id,
                intention_description,
                embedding_text,
                actor_id,
                status,
                target_date,
                intention_type
            FROM st_prospective
            WHERE actor_id = ANY($1)
              AND (archival_status IS NULL OR archival_status = 'ACTIVE')
              AND status = 'ACTIVE'
        """
        params: List[Any] = [entity_ids]

        if tenant_id:
            query += " AND tenant_id = $2"
            params.append(tenant_id)

        query += f" ORDER BY target_date ASC NULLS LAST LIMIT {self.max_per_layer}"

        try:
            rows = await conn.fetch(query, *params)
            return [dict(r) for r in rows if r["intention_id"] not in exclude]
        except Exception as e:
            logger.warning(
                "RelatedContextFetcher: failed to fetch intentions",
                extra={"error": str(e)},
            )
            return []
