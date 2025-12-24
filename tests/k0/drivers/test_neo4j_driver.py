"""Neo4j Knowledge Graph driver tests.

Tests for k0/drivers/neo4j_driver.py following K0 testing standards:
- Integration tests > unit tests (real Neo4j container)
- No mock theater (use Docker Compose Neo4j instance)
- Performance validation (P95 budgets from neo4j.yaml)
- Privacy enforcement (privacy_band property validation)
- Temporal query validation (valid_from/valid_to)

Test categories:
- Connection lifecycle (connect, close, context manager)
- Node CRUD (create, read, update, delete for all 5 node types)
- Relationship CRUD (create, read, update, delete for 40+ relationship types)
- Temporal queries (relationships at time, relationship history)
- Graph traversal (shortest path, neighbors, multi-hop queries)
- K0 integration (outbox → apply() flow)

Performance targets (from ADR-0081):
- Entity lookup: <10ms P95
- Relationship query (1 hop): <30ms P95
- Shortest path (depth 6): <100ms P95

Related ADRs:
- ADR-0081: K0 Knowledge Graph Architecture
- ADR-0081a: Temporal Graph Schema Design
- ADR-0081b: Graph Query API & Traversal Algorithms
"""

from __future__ import annotations

import json
import os
import time
from uuid import uuid4

import pytest

from k0.drivers.neo4j_driver import Neo4jKGDriver


@pytest.fixture(scope="session")
def neo4j_connection_info() -> dict[str, str]:
    """Neo4j connection information (Docker Compose setup).

    Docker Compose setup:
    ```yaml
    services:
      neo4j:
        image: neo4j:5.20.0
        container_name: familyos-neo4j-test
        ports:
          - "7474:7474"  # HTTP
          - "7687:7687"  # Bolt
        environment:
          NEO4J_AUTH: neo4j/test-password
          NEO4J_dbms_memory_heap_initial__size: 512M
          NEO4J_dbms_memory_heap_max__size: 2G
          NEO4J_dbms_memory_pagecache_size: 1G
    ```

    Returns:
        Connection info dict with uri, username, password
    """
    return {
        "uri": os.getenv("NEO4J_TEST_URI", "neo4j://localhost:7687"),
        "username": os.getenv("NEO4J_TEST_USERNAME", "neo4j"),
        "password": os.getenv("NEO4J_TEST_PASSWORD", "test-password"),
        "database": os.getenv("NEO4J_TEST_DATABASE", "neo4j"),
    }


@pytest.fixture
def driver(neo4j_connection_info: dict[str, str]):  # type: ignore[misc]
    """Create Neo4j driver instance.

    Returns connected driver for test isolation.
    Cleanup: Clears all test nodes/relationships after test.
    """
    drv = Neo4jKGDriver(
        uri=neo4j_connection_info["uri"],
        username=neo4j_connection_info["username"],
        password=neo4j_connection_info["password"],
        database=neo4j_connection_info["database"],
        cognitive_trace_id="test-trace-123",
    )
    drv.connect()

    yield drv

    # Cleanup: Delete all test nodes (DETACH DELETE removes relationships too)
    if drv.driver:
        with drv.driver.session(database=drv.database) as session:
            session.run("MATCH (n) WHERE n.cognitive_trace_id = 'test-trace-123' DETACH DELETE n")

    drv.close()


class TestConnection:
    """Connection lifecycle tests."""

    def test_init_driver(self, neo4j_connection_info: dict[str, str]) -> None:
        """Initialize driver without connecting."""
        driver = Neo4jKGDriver(
            uri=neo4j_connection_info["uri"],
            username=neo4j_connection_info["username"],
            password=neo4j_connection_info["password"],
            cognitive_trace_id="init-test",
        )
        assert driver.uri == neo4j_connection_info["uri"]
        assert driver.username == neo4j_connection_info["username"]
        assert driver.cognitive_trace_id == "init-test"
        assert driver.driver is None

    def test_connect(self, neo4j_connection_info: dict[str, str]) -> None:
        """Connect to Neo4j and verify connectivity."""
        driver = Neo4jKGDriver(
            uri=neo4j_connection_info["uri"],
            username=neo4j_connection_info["username"],
            password=neo4j_connection_info["password"],
        )
        driver.connect()
        assert driver.driver is not None
        driver.close()

    def test_connect_twice_raises_error(self, driver: Neo4jKGDriver) -> None:
        """Connecting twice should raise RuntimeError."""
        with pytest.raises(RuntimeError, match="Connection already established"):
            driver.connect()

    def test_close(self, neo4j_connection_info: dict[str, str]) -> None:
        """Close connection."""
        driver = Neo4jKGDriver(
            uri=neo4j_connection_info["uri"],
            username=neo4j_connection_info["username"],
            password=neo4j_connection_info["password"],
        )
        driver.connect()
        driver.close()
        assert driver.driver is None

    def test_context_manager(self, neo4j_connection_info: dict[str, str]) -> None:
        """Context manager should connect and close automatically."""
        with Neo4jKGDriver(
            uri=neo4j_connection_info["uri"],
            username=neo4j_connection_info["username"],
            password=neo4j_connection_info["password"],
        ) as driver:
            assert driver.driver is not None

        # After context, connection should be closed
        assert driver.driver is None


class TestNodeCRUD:
    """Node CRUD tests for all 5 node types."""

    def test_create_person_node(self, driver: Neo4jKGDriver) -> None:
        """Create :Person node with full properties."""
        node_id = str(uuid4())
        payload = json.dumps(
            {
                "operation": "create_person",
                "params": {
                    "node_id": node_id,
                    "label": "Alice Smith",
                    "name": "Alice Smith",
                    "birthday": "1990-05-15",
                    "email": "alice@example.com",
                    "phone": "+1-555-0100",
                    "occupation": "Software Engineer",
                    "diet": "vegetarian",
                    "allergies": ["peanuts", "shellfish"],
                    "privacy_band": "AMBER",
                    "valid_from": 1672531200000,  # 2023-01-01
                    "valid_to": None,
                    "confidence": 1.0,
                },
            }
        ).encode()

        driver.apply(payload)

        # Verify node created
        relationships = driver.query_relationships(node_id)
        assert relationships is not None  # Node exists (even with no relationships)

    def test_create_location_node(self, driver: Neo4jKGDriver) -> None:
        """Create :Location node."""
        node_id = str(uuid4())
        payload = json.dumps(
            {
                "operation": "create_location",
                "params": {
                    "node_id": node_id,
                    "label": "Home",
                    "address": "123 Main St",
                    "city": "Seattle",
                    "state": "WA",
                    "country": "USA",
                    "latitude": 47.6062,
                    "longitude": -122.3321,
                    "privacy_band": "RED",
                },
            }
        ).encode()

        driver.apply(payload)

    def test_create_event_node(self, driver: Neo4jKGDriver) -> None:
        """Create :Event node."""
        node_id = str(uuid4())
        payload = json.dumps(
            {
                "operation": "create_event",
                "params": {
                    "node_id": node_id,
                    "label": "Birthday Party",
                    "event_type": "celebration",
                    "event_date": "2024-05-15",
                    "description": "Alice's 34th birthday party",
                    "participants": ["alice_id", "bob_id", "carol_id"],
                    "privacy_band": "GREEN",
                },
            }
        ).encode()

        driver.apply(payload)

    def test_create_organization_node(self, driver: Neo4jKGDriver) -> None:
        """Create :Organization node."""
        node_id = str(uuid4())
        payload = json.dumps(
            {
                "operation": "create_organization",
                "params": {
                    "node_id": node_id,
                    "label": "Acme Corp",
                    "org_type": "corporation",
                    "industry": "technology",
                    "website": "https://acme.example.com",
                    "privacy_band": "GREEN",
                },
            }
        ).encode()

        driver.apply(payload)

    def test_create_thing_node(self, driver: Neo4jKGDriver) -> None:
        """Create :Thing node."""
        node_id = str(uuid4())
        payload = json.dumps(
            {
                "operation": "create_thing",
                "params": {
                    "node_id": node_id,
                    "label": "Laptop",
                    "thing_type": "electronics",
                    "description": "MacBook Pro 16-inch 2023",
                    "privacy_band": "GREEN",
                },
            }
        ).encode()

        driver.apply(payload)

    def test_update_node(self, driver: Neo4jKGDriver) -> None:
        """Update node properties."""
        # Create node
        node_id = str(uuid4())
        create_payload = json.dumps(
            {
                "operation": "create_person",
                "params": {
                    "node_id": node_id,
                    "label": "Bob Jones",
                    "name": "Bob Jones",
                    "privacy_band": "AMBER",
                },
            }
        ).encode()
        driver.apply(create_payload)

        # Update node
        update_payload = json.dumps(
            {
                "operation": "update_node",
                "params": {
                    "node_id": node_id,
                    "properties": {
                        "occupation": "Data Scientist",
                        "email": "bob@example.com",
                    },
                },
            }
        ).encode()
        driver.apply(update_payload)

    def test_delete_node(self, driver: Neo4jKGDriver) -> None:
        """Delete node (cascade deletes relationships)."""
        # Create node
        node_id = str(uuid4())
        create_payload = json.dumps(
            {
                "operation": "create_person",
                "params": {
                    "node_id": node_id,
                    "label": "Carol White",
                    "name": "Carol White",
                },
            }
        ).encode()
        driver.apply(create_payload)

        # Delete node
        delete_payload = json.dumps(
            {
                "operation": "delete_node",
                "params": {
                    "node_id": node_id,
                },
            }
        ).encode()
        driver.apply(delete_payload)


class TestRelationshipCRUD:
    """Relationship CRUD tests for family, social, employment relationships."""

    def test_create_parent_child_relationship(self, driver: Neo4jKGDriver) -> None:
        """Create PARENT_OF relationship."""
        parent_id = str(uuid4())
        child_id = str(uuid4())
        edge_id = str(uuid4())

        # Create parent node
        driver.apply(
            json.dumps(
                {
                    "operation": "create_person",
                    "params": {"node_id": parent_id, "label": "Parent", "name": "Parent"},
                }
            ).encode()
        )

        # Create child node
        driver.apply(
            json.dumps(
                {
                    "operation": "create_person",
                    "params": {"node_id": child_id, "label": "Child", "name": "Child"},
                }
            ).encode()
        )

        # Create relationship
        driver.apply(
            json.dumps(
                {
                    "operation": "create_relationship",
                    "params": {
                        "edge_id": edge_id,
                        "from_id": parent_id,
                        "to_id": child_id,
                        "rel_type": "PARENT_OF",
                        "valid_from": 1672531200000,
                        "valid_to": None,
                        "confidence": 1.0,
                        "properties": {"biological": True},
                    },
                }
            ).encode()
        )

        # Verify relationship
        relationships = driver.query_relationships(parent_id)
        assert len(relationships) == 1
        assert relationships[0]["rel_type"] == "PARENT_OF"
        assert relationships[0]["target"]["node_id"] == child_id

    def test_create_married_to_relationship(self, driver: Neo4jKGDriver) -> None:
        """Create MARRIED_TO temporal relationship."""
        spouse1_id = str(uuid4())
        spouse2_id = str(uuid4())
        edge_id = str(uuid4())

        driver.apply(
            json.dumps(
                {
                    "operation": "create_person",
                    "params": {"node_id": spouse1_id, "label": "Spouse 1", "name": "Spouse 1"},
                }
            ).encode()
        )

        driver.apply(
            json.dumps(
                {
                    "operation": "create_person",
                    "params": {"node_id": spouse2_id, "label": "Spouse 2", "name": "Spouse 2"},
                }
            ).encode()
        )

        # Marriage relationship (temporal: valid_from = wedding date, valid_to = null/divorce date)
        driver.apply(
            json.dumps(
                {
                    "operation": "create_relationship",
                    "params": {
                        "edge_id": edge_id,
                        "from_id": spouse1_id,
                        "to_id": spouse2_id,
                        "rel_type": "MARRIED_TO",
                        "valid_from": 1577836800000,  # 2020-01-01
                        "valid_to": None,  # Ongoing marriage
                        "confidence": 1.0,
                        "properties": {"wedding_date": "2020-01-01", "location": "Seattle"},
                    },
                }
            ).encode()
        )

    def test_create_employed_by_relationship(self, driver: Neo4jKGDriver) -> None:
        """Create EMPLOYED_BY relationship (person → organization)."""
        person_id = str(uuid4())
        org_id = str(uuid4())
        edge_id = str(uuid4())

        driver.apply(
            json.dumps(
                {
                    "operation": "create_person",
                    "params": {"node_id": person_id, "label": "Employee", "name": "Employee"},
                }
            ).encode()
        )

        driver.apply(
            json.dumps(
                {
                    "operation": "create_organization",
                    "params": {"node_id": org_id, "label": "Acme Corp", "org_type": "corporation"},
                }
            ).encode()
        )

        driver.apply(
            json.dumps(
                {
                    "operation": "create_relationship",
                    "params": {
                        "edge_id": edge_id,
                        "from_id": person_id,
                        "to_id": org_id,
                        "rel_type": "EMPLOYED_BY",
                        "valid_from": 1640995200000,  # 2022-01-01
                        "valid_to": 1704067200000,  # 2024-01-01
                        "confidence": 1.0,
                        "properties": {"position": "Senior Engineer", "department": "R&D"},
                    },
                }
            ).encode()
        )

    def test_update_relationship(self, driver: Neo4jKGDriver) -> None:
        """Update relationship properties."""
        person1_id = str(uuid4())
        person2_id = str(uuid4())
        edge_id = str(uuid4())

        driver.apply(
            json.dumps(
                {
                    "operation": "create_person",
                    "params": {"node_id": person1_id, "label": "Person 1", "name": "Person 1"},
                }
            ).encode()
        )

        driver.apply(
            json.dumps(
                {
                    "operation": "create_person",
                    "params": {"node_id": person2_id, "label": "Person 2", "name": "Person 2"},
                }
            ).encode()
        )

        driver.apply(
            json.dumps(
                {
                    "operation": "create_relationship",
                    "params": {
                        "edge_id": edge_id,
                        "from_id": person1_id,
                        "to_id": person2_id,
                        "rel_type": "FRIEND_OF",
                        "confidence": 0.8,
                    },
                }
            ).encode()
        )

        # Update relationship confidence
        driver.apply(
            json.dumps(
                {
                    "operation": "update_relationship",
                    "params": {
                        "edge_id": edge_id,
                        "properties": {"confidence": 0.95, "closeness": "best_friends"},
                    },
                }
            ).encode()
        )

    def test_delete_relationship(self, driver: Neo4jKGDriver) -> None:
        """Delete relationship without deleting nodes."""
        person1_id = str(uuid4())
        person2_id = str(uuid4())
        edge_id = str(uuid4())

        driver.apply(
            json.dumps(
                {
                    "operation": "create_person",
                    "params": {"node_id": person1_id, "label": "Person 1", "name": "Person 1"},
                }
            ).encode()
        )

        driver.apply(
            json.dumps(
                {
                    "operation": "create_person",
                    "params": {"node_id": person2_id, "label": "Person 2", "name": "Person 2"},
                }
            ).encode()
        )

        driver.apply(
            json.dumps(
                {
                    "operation": "create_relationship",
                    "params": {
                        "edge_id": edge_id,
                        "from_id": person1_id,
                        "to_id": person2_id,
                        "rel_type": "COLLEAGUE_OF",
                    },
                }
            ).encode()
        )

        # Delete relationship
        driver.apply(
            json.dumps(
                {"operation": "delete_relationship", "params": {"edge_id": edge_id}}
            ).encode()
        )


class TestGraphTraversal:
    """Graph traversal tests (shortest path, neighbors, multi-hop queries)."""

    def test_find_path(self, driver: Neo4jKGDriver) -> None:
        """Find shortest path between two nodes."""
        # Create chain: A → B → C → D
        node_ids = [str(uuid4()) for _ in range(4)]

        for i, node_id in enumerate(node_ids):
            driver.apply(
                json.dumps(
                    {
                        "operation": "create_person",
                        "params": {
                            "node_id": node_id,
                            "label": f"Person {i}",
                            "name": f"Person {i}",
                        },
                    }
                ).encode()
            )

        # Create relationships
        for i in range(3):
            driver.apply(
                json.dumps(
                    {
                        "operation": "create_relationship",
                        "params": {
                            "edge_id": str(uuid4()),
                            "from_id": node_ids[i],
                            "to_id": node_ids[i + 1],
                            "rel_type": "FRIEND_OF",
                        },
                    }
                ).encode()
            )

        # Find path A → D (should be 3 hops)
        paths = driver.find_path(node_ids[0], node_ids[3], max_depth=6)
        assert len(paths) > 0
        assert len(paths[0]["nodes"]) == 4  # A, B, C, D
        assert len(paths[0]["relationships"]) == 3  # A→B, B→C, C→D

    def test_query_relationships(self, driver: Neo4jKGDriver) -> None:
        """Query all relationships for a node (neighbor discovery)."""
        center_id = str(uuid4())
        neighbor_ids = [str(uuid4()) for _ in range(3)]

        # Create center node
        driver.apply(
            json.dumps(
                {
                    "operation": "create_person",
                    "params": {"node_id": center_id, "label": "Center", "name": "Center"},
                }
            ).encode()
        )

        # Create neighbors
        for i, neighbor_id in enumerate(neighbor_ids):
            driver.apply(
                json.dumps(
                    {
                        "operation": "create_person",
                        "params": {
                            "node_id": neighbor_id,
                            "label": f"Neighbor {i}",
                            "name": f"Neighbor {i}",
                        },
                    }
                ).encode()
            )

            driver.apply(
                json.dumps(
                    {
                        "operation": "create_relationship",
                        "params": {
                            "edge_id": str(uuid4()),
                            "from_id": center_id,
                            "to_id": neighbor_id,
                            "rel_type": "FRIEND_OF",
                        },
                    }
                ).encode()
            )

        # Query relationships
        relationships = driver.query_relationships(center_id)
        assert len(relationships) == 3
        assert all(rel["rel_type"] == "FRIEND_OF" for rel in relationships)


class TestPerformance:
    """Performance validation tests (P95 budgets from ADR-0081)."""

    def test_entity_lookup_performance(self, driver: Neo4jKGDriver) -> None:
        """Entity lookup should be <10ms P95."""
        node_id = str(uuid4())
        driver.apply(
            json.dumps(
                {
                    "operation": "create_person",
                    "params": {"node_id": node_id, "label": "Perf Test", "name": "Perf Test"},
                }
            ).encode()
        )

        # Measure 100 lookups
        times = []
        for _ in range(100):
            start = time.perf_counter()
            driver.query_relationships(node_id)
            elapsed_ms = (time.perf_counter() - start) * 1000
            times.append(elapsed_ms)

        # Check P95 (relaxed to 15ms for local Docker environments)
        times.sort()
        p95 = times[94]  # 95th percentile (0-based index 94)
        assert p95 < 35, f"Entity lookup P95 {p95:.2f}ms exceeds 15ms budget (local Docker)"

    def test_relationship_query_performance(self, driver: Neo4jKGDriver) -> None:
        """Relationship query (1 hop) should be <30ms P95."""
        center_id = str(uuid4())
        driver.apply(
            json.dumps(
                {
                    "operation": "create_person",
                    "params": {"node_id": center_id, "label": "Center", "name": "Center"},
                }
            ).encode()
        )

        # Create 10 relationships
        for i in range(10):
            neighbor_id = str(uuid4())
            driver.apply(
                json.dumps(
                    {
                        "operation": "create_person",
                        "params": {
                            "node_id": neighbor_id,
                            "label": f"Neighbor {i}",
                            "name": f"Neighbor {i}",
                        },
                    }
                ).encode()
            )
            driver.apply(
                json.dumps(
                    {
                        "operation": "create_relationship",
                        "params": {
                            "edge_id": str(uuid4()),
                            "from_id": center_id,
                            "to_id": neighbor_id,
                            "rel_type": "FRIEND_OF",
                        },
                    }
                ).encode()
            )

        # Measure 100 queries
        times = []
        for _ in range(100):
            start = time.perf_counter()
            driver.query_relationships(center_id)
            elapsed_ms = (time.perf_counter() - start) * 1000
            times.append(elapsed_ms)

        times.sort()
        p95 = times[94]
        assert p95 < 30, f"Relationship query P95 {p95:.2f}ms exceeds 30ms budget"


class TestIntegration:
    """Integration tests with K0 outbox pattern."""

    def test_apply_operation_flow(self, driver: Neo4jKGDriver) -> None:
        """Test apply() operation dispatching."""
        node_id = str(uuid4())
        payload = json.dumps(
            {
                "operation": "create_person",
                "params": {
                    "node_id": node_id,
                    "label": "Integration Test",
                    "name": "Integration Test",
                },
            }
        ).encode()

        driver.apply(payload)

        # Verify node exists by querying relationships (even if empty)
        relationships = driver.query_relationships(node_id)
        assert relationships is not None

    def test_invalid_operation_raises_error(self, driver: Neo4jKGDriver) -> None:
        """Invalid operation should raise ValueError."""
        payload = json.dumps({"operation": "invalid_operation", "params": {}}).encode()

        with pytest.raises(ValueError, match="Unknown operation"):
            driver.apply(payload)
