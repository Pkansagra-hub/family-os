"""
EntityGraphExpander - GAP-001 Milestone 5 (Issue 5.2)

Traverses st_kg_dom → st_kg_edges to expand entity set.
Returns 1-hop neighbors with edge weights.

GAP Reference: GAP_001 Section 6 (Entity Graph Expansion)
Spec Reference: D:\\familyos\\docs\\plans\\GAP_001_MILESTONE_5_CONTEXT_EXPANDER.md
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class ExpandedEntity:
    """
    An entity with its expansion path.

    Attributes:
        entity_id: Unique entity identifier
        canonical_name: Human-readable name
        entity_type: Type (PERSON, PLACE, ORGANIZATION, etc.)
        hop_distance: Distance from seed (0 = seed, 1 = neighbor)
        via_edge_type: Edge type used to reach this entity
        edge_weight: Weight of the traversed edge
    """

    entity_id: str
    canonical_name: str
    entity_type: Optional[str] = None
    hop_distance: int = 0
    via_edge_type: Optional[str] = None
    edge_weight: float = 1.0

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "entity_id": self.entity_id,
            "canonical_name": self.canonical_name,
            "entity_type": self.entity_type,
            "hop_distance": self.hop_distance,
            "via_edge_type": self.via_edge_type,
            "edge_weight": self.edge_weight,
        }


@dataclass
class ExpansionResult:
    """
    Result of entity graph expansion.

    Attributes:
        entities: List of all entities (seeds + neighbors)
        seed_count: Number of seed entities
        expanded_count: Number of neighbor entities added
        edge_types_traversed: Set of edge types used
    """

    entities: List[ExpandedEntity] = field(default_factory=list)
    seed_count: int = 0
    expanded_count: int = 0
    edge_types_traversed: Set[str] = field(default_factory=set)

    def get_all_entity_ids(self) -> Set[str]:
        """Get all entity IDs in the result."""
        return {e.entity_id for e in self.entities}

    def get_seed_ids(self) -> Set[str]:
        """Get seed entity IDs only."""
        return {e.entity_id for e in self.entities if e.hop_distance == 0}

    def get_neighbor_ids(self) -> Set[str]:
        """Get neighbor entity IDs only."""
        return {e.entity_id for e in self.entities if e.hop_distance > 0}

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "seed_count": self.seed_count,
            "expanded_count": self.expanded_count,
            "total_entities": len(self.entities),
            "edge_types": list(self.edge_types_traversed),
        }


class EntityGraphExpander:
    """
    Expands entity set via graph traversal.

    Traverses st_kg_edges to find entities connected to the seed set.
    Supports configurable traversal depth and edge weight filtering.

    Usage:
        expander = EntityGraphExpander(max_hops=1, min_edge_weight=0.5)
        result = await expander.expand({"Mom", "Dad"}, conn)
        for entity in result.entities:
            print(f"{entity.canonical_name} (hop {entity.hop_distance})")
    """

    def __init__(
        self,
        max_hops: int = 1,
        min_edge_weight: float = 0.5,
        max_neighbors: int = 20,
    ):
        """
        Initialize expander.

        Args:
            max_hops: Maximum traversal depth (default 1)
            min_edge_weight: Minimum edge weight to traverse
            max_neighbors: Maximum neighbors per entity
        """
        self.max_hops = max_hops
        self.min_edge_weight = min_edge_weight
        self.max_neighbors = max_neighbors

    async def expand(
        self,
        entity_ids: Set[str],
        conn: Any,
        tenant_id: Optional[str] = None,
    ) -> ExpansionResult:
        """
        Expand entity set via graph traversal.

        Args:
            entity_ids: Seed entity IDs
            conn: asyncpg database connection
            tenant_id: Optional tenant filter

        Returns:
            ExpansionResult with expanded entities
        """
        if not entity_ids:
            return ExpansionResult(
                entities=[],
                seed_count=0,
                expanded_count=0,
            )

        # Fetch seed entities from st_kg_dom
        seed_entities = await self._fetch_entities(list(entity_ids), conn, tenant_id)

        result_entities: List[ExpandedEntity] = []

        # Add seeds to result
        for e in seed_entities:
            result_entities.append(
                ExpandedEntity(
                    entity_id=e["entity_id"],
                    canonical_name=e.get("canonical_name") or e["entity_id"],
                    entity_type=e.get("entity_type"),
                    hop_distance=0,
                )
            )

        # If max_hops == 0, return only seeds
        if self.max_hops == 0:
            return ExpansionResult(
                entities=result_entities,
                seed_count=len(entity_ids),
                expanded_count=0,
            )

        # Traverse edges to find neighbors
        neighbors, edge_types = await self._find_neighbors(entity_ids, conn, tenant_id)

        # Add neighbors to result
        for n in neighbors:
            result_entities.append(
                ExpandedEntity(
                    entity_id=n["entity_id"],
                    canonical_name=n.get("canonical_name") or n["entity_id"],
                    entity_type=n.get("entity_type"),
                    hop_distance=1,
                    via_edge_type=n.get("edge_type"),
                    edge_weight=n.get("edge_weight", 1.0),
                )
            )

        logger.debug(
            "EntityGraphExpander: expansion complete",
            extra={
                "seed_count": len(entity_ids),
                "expanded_count": len(neighbors),
                "edge_types": list(edge_types),
            },
        )

        return ExpansionResult(
            entities=result_entities,
            seed_count=len(entity_ids),
            expanded_count=len(neighbors),
            edge_types_traversed=edge_types,
        )

    async def _fetch_entities(
        self,
        entity_ids: List[str],
        conn: Any,
        tenant_id: Optional[str],
    ) -> List[Dict]:
        """Fetch entity records from st_kg_dom."""
        if not entity_ids:
            return []

        query = """
            SELECT entity_id, canonical_name, entity_type
            FROM st_kg_dom
            WHERE entity_id = ANY($1)
              AND (archival_status IS NULL OR archival_status = 'ACTIVE')
        """
        params: List[Any] = [entity_ids]

        if tenant_id:
            query += " AND tenant_id = $2"
            params.append(tenant_id)

        try:
            rows = await conn.fetch(query, *params)
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning(
                "EntityGraphExpander: failed to fetch entities",
                extra={"error": str(e), "count": len(entity_ids)},
            )
            return []

    async def _find_neighbors(
        self,
        entity_ids: Set[str],
        conn: Any,
        tenant_id: Optional[str],
    ) -> tuple:
        """
        Find 1-hop neighbors via st_kg_edges.

        Returns tuple of (neighbor_entities, edge_types)
        """
        entity_list = list(entity_ids)

        # Query edges in both directions (bidirectional graph)
        query = """
            SELECT
                e.relation_type AS edge_type,
                e.edge_weight,
                CASE
                    WHEN e.source_entity_id = ANY($1) THEN e.target_entity_id
                    ELSE e.source_entity_id
                END AS neighbor_id
            FROM st_kg_edges e
            WHERE (e.source_entity_id = ANY($1) OR e.target_entity_id = ANY($1))
              AND e.edge_weight >= $2
              AND (e.archival_status IS NULL OR e.archival_status = 'ACTIVE')
        """
        params: List[Any] = [entity_list, self.min_edge_weight]

        if tenant_id:
            query += " AND e.tenant_id = $3"
            params.append(tenant_id)

        # Limit total edges returned
        query += f" LIMIT {self.max_neighbors * len(entity_ids)}"

        try:
            edge_rows = await conn.fetch(query, *params)
        except Exception as e:
            logger.warning(
                "EntityGraphExpander: failed to query edges",
                extra={"error": str(e)},
            )
            return [], set()

        # Collect unique neighbor IDs (excluding seeds)
        neighbor_ids: Set[str] = set()
        edge_types: Set[str] = set()
        edge_info: Dict[str, Dict] = {}

        for row in edge_rows:
            neighbor_id = row["neighbor_id"]
            if neighbor_id not in entity_ids:
                neighbor_ids.add(neighbor_id)
                edge_types.add(row["edge_type"])
                # Store edge info for later
                if neighbor_id not in edge_info:
                    edge_info[neighbor_id] = {
                        "edge_type": row["edge_type"],
                        "edge_weight": row["edge_weight"],
                    }

        if not neighbor_ids:
            return [], edge_types

        # Limit neighbors
        limited_ids = list(neighbor_ids)[: self.max_neighbors]

        # Fetch neighbor entities from st_kg_dom
        neighbor_entities = await self._fetch_entities(limited_ids, conn, tenant_id)

        # Attach edge info to neighbor records
        for n in neighbor_entities:
            eid = n["entity_id"]
            if eid in edge_info:
                n["edge_type"] = edge_info[eid]["edge_type"]
                n["edge_weight"] = edge_info[eid]["edge_weight"]

        return neighbor_entities, edge_types

    async def expand_multi_hop(
        self,
        entity_ids: Set[str],
        conn: Any,
        tenant_id: Optional[str] = None,
    ) -> ExpansionResult:
        """
        Expand entity set with multiple hops.

        Note: Currently only 1-hop is implemented. Multi-hop would
        require recursive traversal with visited tracking.

        Args:
            entity_ids: Seed entity IDs
            conn: Database connection
            tenant_id: Optional tenant filter

        Returns:
            ExpansionResult with expanded entities
        """
        # For now, delegate to single-hop expansion
        # Multi-hop can be added later if needed
        return await self.expand(entity_ids, conn, tenant_id)
