"""
EntityExtractor - GAP-001 Milestone 5 (Issue 5.1)

Extracts entity IDs from truth layer records.
Handles different column patterns per layer.

GAP Reference: GAP_001 Section 5.6 (Entity Graph as Universal Linker)
Spec Reference: D:\\familyos\\docs\\plans\\GAP_001_MILESTONE_5_CONTEXT_EXPANDER.md
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Set

logger = logging.getLogger(__name__)


# Entity columns per layer - defines which columns contain entity references
ENTITY_COLUMNS: Dict[str, Dict[str, List[str]]] = {
    "st_epi": {
        "array": ["participants_json"],  # JSON array of entity IDs
        "scalar": [],
    },
    "st_sem": {
        "array": [],
        "scalar": ["actor_id"],  # Single entity ID
    },
    "st_procedural": {
        "array": [],
        "scalar": ["actor_id"],
    },
    "st_social": {
        "array": [],
        "scalar": ["actor_a_id", "actor_b_id"],  # Two entity IDs
    },
    "st_prospective": {
        "array": ["related_entities_json"],
        "scalar": ["actor_id"],
    },
    "st_kg_dom": {
        "array": [],
        "scalar": ["entity_id", "canonical_name"],  # Both ID and canonical name for linking
    },
    "st_kg_edges": {
        "array": [],
        "scalar": ["source_entity_id", "target_entity_id"],
    },
}


@dataclass
class ExtractionResult:
    """
    Result of entity extraction.

    Attributes:
        entity_ids: Set of all unique entity IDs found
        by_layer: Entity IDs grouped by source layer
        record_count: Number of records processed
    """

    entity_ids: Set[str] = field(default_factory=set)
    by_layer: Dict[str, Set[str]] = field(default_factory=dict)
    record_count: int = 0

    def merge(self, other: ExtractionResult) -> ExtractionResult:
        """Merge another extraction result into this one."""
        merged_ids = self.entity_ids | other.entity_ids
        merged_by_layer = dict(self.by_layer)

        for layer, ids in other.by_layer.items():
            if layer in merged_by_layer:
                merged_by_layer[layer] = merged_by_layer[layer] | ids
            else:
                merged_by_layer[layer] = ids

        return ExtractionResult(
            entity_ids=merged_ids,
            by_layer=merged_by_layer,
            record_count=self.record_count + other.record_count,
        )

    def to_dict(self) -> Dict:
        """Convert to dictionary for logging."""
        return {
            "entity_count": len(self.entity_ids),
            "record_count": self.record_count,
            "layers": {k: len(v) for k, v in self.by_layer.items()},
        }


class EntityExtractor:
    """
    Extracts entity IDs from truth layer records.

    Different truth layers store entity references in different columns:
    - st_epi: participants_json (JSON array)
    - st_sem: actor_id (scalar)
    - st_social: actor_a_id, actor_b_id (two scalars)
    - st_kg_dom: entity_id IS the entity
    - st_kg_edges: source_entity_id, target_entity_id

    Usage:
        extractor = EntityExtractor()
        result = extractor.extract_from_records(records, "st_epi")
        print(result.entity_ids)  # {"Mom", "Dad", "User"}
    """

    def extract_from_records(
        self,
        records: List[Dict[str, Any]],
        layer: str,
    ) -> ExtractionResult:
        """
        Extract entity IDs from records of a specific layer.

        Args:
            records: List of record dictionaries
            layer: Source layer name (st_epi, st_sem, etc.)

        Returns:
            ExtractionResult with unique entity IDs
        """
        entities: Set[str] = set()
        config = ENTITY_COLUMNS.get(layer, {"array": [], "scalar": []})

        for record in records:
            # Handle array columns (JSON arrays of entity IDs)
            for col in config["array"]:
                if col in record and record[col]:
                    try:
                        value = record[col]
                        if isinstance(value, str):
                            arr = json.loads(value)
                        elif isinstance(value, list):
                            arr = value
                        else:
                            continue

                        for entity_id in arr:
                            if entity_id and isinstance(entity_id, str):
                                entities.add(entity_id)
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.debug(
                            f"EntityExtractor: failed to parse {col}",
                            extra={"error": str(e)},
                        )

            # Handle scalar columns (single entity ID)
            for col in config["scalar"]:
                if col in record and record[col]:
                    entity_id = record[col]
                    if isinstance(entity_id, str):
                        entities.add(entity_id)

        return ExtractionResult(
            entity_ids=entities,
            by_layer={layer: entities} if entities else {},
            record_count=len(records),
        )

    def extract_from_search_results(
        self,
        results: List[tuple],  # [(layer, record_id, score), ...]
        records_by_id: Dict[str, Dict[str, Any]],
    ) -> ExtractionResult:
        """
        Extract entities from vector search results.

        Args:
            results: Search results with (layer, record_id, score)
            records_by_id: Pre-fetched records keyed by record ID

        Returns:
            ExtractionResult with all unique entities
        """
        all_entities: Set[str] = set()
        by_layer: Dict[str, Set[str]] = {}

        for layer, record_id, score in results:
            if record_id not in records_by_id:
                logger.debug(
                    "EntityExtractor: record not found",
                    extra={"layer": layer, "record_id": record_id},
                )
                continue

            record = records_by_id[record_id]
            result = self.extract_from_records([record], layer)

            all_entities.update(result.entity_ids)

            if layer not in by_layer:
                by_layer[layer] = set()
            by_layer[layer].update(result.entity_ids)

        return ExtractionResult(
            entity_ids=all_entities,
            by_layer=by_layer,
            record_count=len(results),
        )

    def extract_from_record(
        self,
        record: Dict[str, Any],
        layer: str,
    ) -> Set[str]:
        """
        Extract entities from a single record.

        Convenience method for extracting from one record.

        Args:
            record: Single record dictionary
            layer: Source layer name

        Returns:
            Set of entity IDs
        """
        result = self.extract_from_records([record], layer)
        return result.entity_ids
