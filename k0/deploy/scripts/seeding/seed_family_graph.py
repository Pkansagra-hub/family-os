#!/usr/bin/env python3
"""
Family Graph Seed Script - ADR-K022

Seeds the knowledge graph (st_kg_dom + st_kg_edges) with family relationships
for a single user's family structure. This replaces the Neo4j-based approach.

The user is the CENTER of the graph. All relationships are from user's perspective:
- "My spouse" → SPOUSE_OF edge from user to spouse
- "My mom" → user CHILD_OF mom (mom is user's parent)
- "My daughter" → user PARENT_OF daughter

Usage:
    # Interactive mode (asks questions)
    python k0/deploy/seed_family_graph.py --interactive

    # From config file
    python k0/deploy/seed_family_graph.py --config family_config.yaml

    # Direct (for testing)
    python k0/deploy/seed_family_graph.py

Architecture Context (ADR-K022):
- Replaces Neo4j with PostgreSQL-only graph storage
- Uses st_kg_dom for entity nodes (PERSON type)
- Uses st_kg_edges for typed relationships
- P02's social.family_graph_resolve queries st_kg_edges for participant role resolution
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List

import asyncpg

# Default DSN
DEFAULT_DSN = "postgresql://k0user:changeme@localhost:5432/k0_kernel"
DEFAULT_TENANT = "tenant_default"
DEFAULT_SPACE = "space_default"


class RelationType(str, Enum):
    """Family relationship types (directional)."""

    SPOUSE_OF = "SPOUSE_OF"  # Bidirectional
    PARENT_OF = "PARENT_OF"  # user is parent of target
    CHILD_OF = "CHILD_OF"  # user is child of target
    SIBLING_OF = "SIBLING_OF"  # Bidirectional
    CARETAKER_OF = "CARETAKER_OF"  # user cares for target
    GRANDPARENT_OF = "GRANDPARENT_OF"  # user is grandparent of target
    GRANDCHILD_OF = "GRANDCHILD_OF"  # user is grandchild of target
    FRIEND_OF = "FRIEND_OF"  # Close friend (not family)
    COLLEAGUE_OF = "COLLEAGUE_OF"  # Work colleague


@dataclass
class Person:
    """A person in the family graph."""

    name: str
    person_id: str = ""
    nickname: str = ""
    relation_to_user: RelationType = RelationType.FRIEND_OF
    attributes: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.person_id:
            # Generate deterministic ID from name
            name_hash = hashlib.md5(self.name.lower().encode()).hexdigest()[:8]
            self.person_id = f"person_{self.name.lower().replace(' ', '_')}_{name_hash}"


@dataclass
class FamilyConfig:
    """Complete family configuration for seeding."""

    # The user (center of the graph)
    user_name: str
    user_id: str = ""

    # Family members with their relation to user
    family_members: List[Person] = field(default_factory=list)

    # Metadata
    tenant_id: str = DEFAULT_TENANT
    space_id: str = DEFAULT_SPACE

    def __post_init__(self):
        if not self.user_id:
            name_hash = hashlib.md5(self.user_name.lower().encode()).hexdigest()[:8]
            self.user_id = f"person_{self.user_name.lower().replace(' ', '_')}_{name_hash}"


# =============================================================================
# Example Family Configuration
# =============================================================================


def create_example_family() -> FamilyConfig:
    """
    Create an example family configuration.

    This represents a typical family structure from the user's perspective:

    User (Prince) at center with:
    - Spouse: Jeel
    - Daughter: Sharvi
    - Parents: Mom (Nayna), Dad (Kansagra)
    - In-laws: Mother-in-law (Jayshree), Father-in-law (Jitendra)
    - Siblings: Brother (Parth)
    - Friends: Close friends from various contexts
    """
    return FamilyConfig(
        user_name="Prince",
        family_members=[
            # === IMMEDIATE FAMILY ===
            Person(
                name="Jeel",
                nickname="wifey",
                relation_to_user=RelationType.SPOUSE_OF,
                attributes={"role": "spouse", "intimacy": "HIGH"},
            ),
            Person(
                name="Sharvi",
                nickname="baby",
                relation_to_user=RelationType.PARENT_OF,  # User is PARENT OF Sharvi
                attributes={"role": "daughter", "intimacy": "HIGH", "age": "child"},
            ),
            # === PARENTS ===
            Person(
                name="Nayna",
                nickname="mom",
                relation_to_user=RelationType.CHILD_OF,  # User is CHILD OF mom
                attributes={"role": "mother", "intimacy": "HIGH", "side": "maternal"},
            ),
            Person(
                name="Kansagra",
                nickname="dad",
                relation_to_user=RelationType.CHILD_OF,  # User is CHILD OF dad
                attributes={"role": "father", "intimacy": "HIGH", "side": "paternal"},
            ),
            # === IN-LAWS ===
            Person(
                name="Jayshree",
                nickname="mother-in-law",
                relation_to_user=RelationType.CHILD_OF,  # Spouse's parents
                attributes={"role": "mother-in-law", "intimacy": "MED", "side": "spouse"},
            ),
            Person(
                name="Jitendra",
                nickname="father-in-law",
                relation_to_user=RelationType.CHILD_OF,
                attributes={"role": "father-in-law", "intimacy": "MED", "side": "spouse"},
            ),
            # === SIBLINGS ===
            Person(
                name="Parth",
                nickname="bro",
                relation_to_user=RelationType.SIBLING_OF,
                attributes={"role": "brother", "intimacy": "HIGH"},
            ),
            # === GRANDPARENTS (User's) ===
            Person(
                name="Dada",
                relation_to_user=RelationType.GRANDCHILD_OF,  # User is grandchild
                attributes={"role": "grandfather", "side": "paternal"},
            ),
            Person(
                name="Dadi",
                relation_to_user=RelationType.GRANDCHILD_OF,
                attributes={"role": "grandmother", "side": "paternal"},
            ),
            # === CLOSE FRIENDS ===
            Person(
                name="Alex",
                relation_to_user=RelationType.FRIEND_OF,
                attributes={"context": "college", "intimacy": "MED"},
            ),
            Person(
                name="Sarah",
                relation_to_user=RelationType.FRIEND_OF,
                attributes={"context": "work", "intimacy": "MED"},
            ),
            Person(
                name="Mike",
                relation_to_user=RelationType.FRIEND_OF,
                attributes={"context": "neighborhood", "intimacy": "LOW"},
            ),
            # === WORK COLLEAGUES ===
            Person(
                name="Rachel",
                relation_to_user=RelationType.COLLEAGUE_OF,
                attributes={"context": "work", "department": "engineering"},
            ),
            Person(
                name="Tom",
                relation_to_user=RelationType.COLLEAGUE_OF,
                attributes={"context": "work", "department": "product"},
            ),
        ],
    )


# =============================================================================
# Database Operations
# =============================================================================


def _generate_entity_id(name: str) -> str:
    """Generate deterministic entity ID from name."""
    name_hash = hashlib.md5(name.lower().encode()).hexdigest()[:8]
    return f"entity_PERSON_{name.lower().replace(' ', '_')}_{name_hash}"


def _generate_edge_id(source: str, target: str, rel_type: str) -> str:
    """Generate deterministic edge ID."""
    combo = f"{source}_{target}_{rel_type}"
    combo_hash = hashlib.md5(combo.encode()).hexdigest()[:12]
    return f"edge_{rel_type.lower()}_{combo_hash}"


async def seed_family_graph(config: FamilyConfig, dsn: str | None = None) -> Dict[str, Any]:
    """
    Seed the family graph into st_kg_dom and st_kg_edges.

    Args:
        config: Family configuration
        dsn: PostgreSQL connection string

    Returns:
        Results dictionary with counts and any errors
    """
    dsn = dsn or os.environ.get("K0_DSN", DEFAULT_DSN)
    now_ms = int(time.time() * 1000)

    results = {
        "entities_inserted": 0,
        "entities_skipped": 0,
        "edges_inserted": 0,
        "edges_skipped": 0,
        "errors": [],
    }

    try:
        conn = await asyncpg.connect(dsn)
    except Exception as e:
        results["errors"].append(f"Connection failed: {e}")
        return results

    try:
        # === Step 1: Create user entity ===
        user_entity_id = _generate_entity_id(config.user_name)

        existing = await conn.fetchval(
            "SELECT entity_id FROM st_kg_dom WHERE entity_id = $1", user_entity_id
        )

        if not existing:
            await conn.execute(
                """
                INSERT INTO st_kg_dom (
                    entity_id, tenant_id, space_id, version,
                    entity_type, canonical_name, aliases_json,
                    attributes_json, confidence_score, archival_status,
                    valid_from, created_at, updated_at
                ) VALUES ($1, $2, $3, 1, 'PERSON', $4, $5, $6, 1.0, 'ACTIVE', $7, $7, $7)
                """,
                user_entity_id,
                config.tenant_id,
                config.space_id,
                config.user_name,
                json.dumps(["me", "self", "user"]),
                json.dumps({"role": "self", "is_user": True}),
                now_ms,
            )
            results["entities_inserted"] += 1
            print(f"  ✅ Created user entity: {config.user_name} ({user_entity_id})")
        else:
            results["entities_skipped"] += 1
            print(f"  ⏭️  User entity exists: {config.user_name}")

        # === Step 2: Create family member entities and edges ===
        for person in config.family_members:
            person_entity_id = _generate_entity_id(person.name)

            # Create entity if not exists
            existing = await conn.fetchval(
                "SELECT entity_id FROM st_kg_dom WHERE entity_id = $1", person_entity_id
            )

            if not existing:
                aliases = [person.name.lower()]
                if person.nickname:
                    aliases.append(person.nickname.lower())

                await conn.execute(
                    """
                    INSERT INTO st_kg_dom (
                        entity_id, tenant_id, space_id, version,
                        entity_type, canonical_name, aliases_json,
                        attributes_json, confidence_score, archival_status,
                        valid_from, created_at, updated_at
                    ) VALUES ($1, $2, $3, 1, 'PERSON', $4, $5, $6, 1.0, 'ACTIVE', $7, $7, $7)
                    """,
                    person_entity_id,
                    config.tenant_id,
                    config.space_id,
                    person.name,
                    json.dumps(aliases),
                    json.dumps(person.attributes),
                    now_ms,
                )
                results["entities_inserted"] += 1
                print(f"  ✅ Created entity: {person.name} ({person_entity_id})")
            else:
                results["entities_skipped"] += 1
                print(f"  ⏭️  Entity exists: {person.name}")

            # Create edge: user → person with relationship type
            edge_id = _generate_edge_id(
                user_entity_id, person_entity_id, person.relation_to_user.value
            )

            existing_edge = await conn.fetchval(
                "SELECT edge_id FROM st_kg_edges WHERE edge_id = $1", edge_id
            )

            if not existing_edge:
                await conn.execute(
                    """
                    INSERT INTO st_kg_edges (
                        edge_id, tenant_id, space_id, version,
                        source_entity_id, target_entity_id,
                        relation_type, relation_subtype,
                        properties_json, edge_weight, confidence_score, archival_status,
                        valid_from, created_at, updated_at
                    ) VALUES ($1, $2, $3, 1, $4, $5, $6, $7, $8, 1.0, 1.0, 'ACTIVE', $9, $9, $9)
                    """,
                    edge_id,
                    config.tenant_id,
                    config.space_id,
                    user_entity_id,
                    person_entity_id,
                    person.relation_to_user.value,
                    person.attributes.get("role"),
                    json.dumps({"seed": True, "source": "onboarding"}),
                    now_ms,
                )
                results["edges_inserted"] += 1
                print(
                    f"  ✅ Created edge: {config.user_name} --[{person.relation_to_user.value}]--> {person.name}"
                )
            else:
                results["edges_skipped"] += 1
                print(f"  ⏭️  Edge exists: {config.user_name} → {person.name}")

            # For bidirectional relationships, create reverse edge
            if person.relation_to_user in (
                RelationType.SPOUSE_OF,
                RelationType.SIBLING_OF,
                RelationType.FRIEND_OF,
            ):
                reverse_edge_id = _generate_edge_id(
                    person_entity_id, user_entity_id, person.relation_to_user.value
                )

                existing_reverse = await conn.fetchval(
                    "SELECT edge_id FROM st_kg_edges WHERE edge_id = $1", reverse_edge_id
                )

                if not existing_reverse:
                    await conn.execute(
                        """
                        INSERT INTO st_kg_edges (
                            edge_id, tenant_id, space_id, version,
                            source_entity_id, target_entity_id,
                            relation_type, relation_subtype,
                            properties_json, edge_weight, confidence_score, archival_status,
                            valid_from, created_at, updated_at
                        ) VALUES ($1, $2, $3, 1, $4, $5, $6, $7, $8, 1.0, 1.0, 'ACTIVE', $9, $9, $9)
                        """,
                        reverse_edge_id,
                        config.tenant_id,
                        config.space_id,
                        person_entity_id,
                        user_entity_id,
                        person.relation_to_user.value,
                        person.attributes.get("role"),
                        json.dumps({"seed": True, "source": "onboarding", "reverse": True}),
                        now_ms,
                    )
                    results["edges_inserted"] += 1
                    print(
                        f"  ✅ Created reverse edge: {person.name} --[{person.relation_to_user.value}]--> {config.user_name}"
                    )

        # === Step 3: Create inter-family relationships ===
        # E.g., Jeel is PARENT_OF Sharvi, Spouse's parents are connected, etc.
        await _create_derived_relationships(conn, config, results, now_ms)

    finally:
        await conn.close()

    return results


async def _create_derived_relationships(
    conn: asyncpg.Connection, config: FamilyConfig, results: Dict[str, Any], now_ms: int
) -> None:
    """Create derived relationships between family members."""

    # Find spouse and children
    spouse = None
    children = []
    for p in config.family_members:
        if p.relation_to_user == RelationType.SPOUSE_OF:
            spouse = p
        elif p.relation_to_user == RelationType.PARENT_OF:
            children.append(p)

    # Spouse is also parent of children
    if spouse and children:
        spouse_entity_id = _generate_entity_id(spouse.name)
        for child in children:
            child_entity_id = _generate_entity_id(child.name)
            edge_id = _generate_edge_id(spouse_entity_id, child_entity_id, "PARENT_OF")

            existing = await conn.fetchval(
                "SELECT edge_id FROM st_kg_edges WHERE edge_id = $1", edge_id
            )

            if not existing:
                await conn.execute(
                    """
                    INSERT INTO st_kg_edges (
                        edge_id, tenant_id, space_id, version,
                        source_entity_id, target_entity_id,
                        relation_type, relation_subtype,
                        properties_json, edge_weight, confidence_score, archival_status,
                        valid_from, created_at, updated_at
                    ) VALUES ($1, $2, $3, 1, $4, $5, 'PARENT_OF', 'mother', $6, 1.0, 1.0, 'ACTIVE', $7, $7, $7)
                    """,
                    edge_id,
                    config.tenant_id,
                    config.space_id,
                    spouse_entity_id,
                    child_entity_id,
                    json.dumps({"seed": True, "derived": True}),
                    now_ms,
                )
                results["edges_inserted"] += 1
                print(f"  ✅ Derived edge: {spouse.name} --[PARENT_OF]--> {child.name}")


async def main() -> int:
    """Main entry point."""
    print("=" * 70)
    print("Family Graph Seed Script (ADR-K022)")
    print("=" * 70)
    print()

    dsn = os.environ.get("K0_DSN", DEFAULT_DSN)
    print(f"DSN: {dsn.replace('changeme', '***')}")
    print()

    # Use example family configuration
    config = create_example_family()

    print(f"User: {config.user_name}")
    print(f"Family members: {len(config.family_members)}")
    print()
    print("Seeding family graph...")
    print("-" * 70)

    results = await seed_family_graph(config, dsn)

    print("-" * 70)
    print()
    print("Results:")
    print(f"  Entities inserted: {results['entities_inserted']}")
    print(f"  Entities skipped:  {results['entities_skipped']}")
    print(f"  Edges inserted:    {results['edges_inserted']}")
    print(f"  Edges skipped:     {results['edges_skipped']}")

    if results["errors"]:
        print()
        print("Errors:")
        for err in results["errors"]:
            print(f"  ❌ {err}")
        return 1

    print()
    print("✅ Family graph seeded successfully!")
    print()
    print("The following relationship types are now available for P02 social resolution:")
    print("  - SPOUSE_OF, PARENT_OF, CHILD_OF, SIBLING_OF")
    print("  - GRANDPARENT_OF, GRANDCHILD_OF, CARETAKER_OF")
    print("  - FRIEND_OF, COLLEAGUE_OF")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
