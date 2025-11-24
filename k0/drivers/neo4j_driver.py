"""Neo4j Knowledge Graph driver for K0 temporal graph storage.

This driver implements the K0 Driver SPI (see K0 README §7) for Neo4j backend.
It provides temporal graph storage with versioning, relationship tracking, and
Cypher query operations.

Architecture:
- Native Neo4j driver (not SQLite-based)
- Temporal properties (valid_from, valid_to) for relationship evolution
- Node labels: Person, Location, Event, Organization, Thing
- Relationship types: Family, Social, Employment, Location, Temporal, etc.

Related ADRs:
- ADR-0081: K0 Knowledge Graph Architecture
- ADR-0081a: Temporal Graph Schema Design
- ADR-0081b: Graph Query API & Traversal Algorithms
- ADR-0081c: Episodic Memory → KG Integration

Configuration:
- k0/config/neo4j.yaml: Connection settings, performance budgets, privacy settings
- requirements.txt: neo4j>=5.20.0
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from neo4j import Driver as Neo4jClient
from neo4j import GraphDatabase, Session
from neo4j.exceptions import Neo4jError

if TYPE_CHECKING:
    from k0.storage.outbox import OutboxEntry

logger = logging.getLogger(__name__)


class Neo4jKGDriver:
    """Neo4j Knowledge Graph driver for K0 temporal graph storage.

    Implements Driver SPI contract for Knowledge Graph:
    - Node operations: create_node, get_node, update_node, delete_node
    - Relationship operations: create_relationship, get_relationships, update_relationship
    - Temporal queries: get_relationships_at_time, get_relationship_history
    - Graph traversal: find_path, get_neighbors, traverse

    Storage responsibilities:
    - Nodes (entities): Person, Location, Event, Organization, Thing
    - Relationships (edges): Family, Social, Employment, Location, Temporal, etc.
    - Temporal properties: valid_from, valid_to, confidence, version history
    - Privacy bands: GREEN, AMBER, RED (integration with K0 P10)
    """

    def __init__(
        self,
        uri: str,
        username: str,
        password: str,
        database: str = "neo4j",
        cognitive_trace_id: str | None = None,
    ) -> None:
        """Initialize Neo4j Knowledge Graph driver.

        Args:
            uri: Neo4j Bolt protocol URI (neo4j://localhost:7687)
            username: Authentication username
            password: Authentication password
            database: Neo4j database name (default: "neo4j")
            cognitive_trace_id: Optional trace ID for observability
        """
        self.uri = uri
        self.username = username
        self.password = password
        self.database = database
        self.cognitive_trace_id = cognitive_trace_id
        self.driver: Neo4jClient | None = None
        logger.info(
            "Neo4jKGDriver initialized",
            extra={
                "uri": uri,
                "database": database,
                "cognitive_trace_id": cognitive_trace_id,
            },
        )

    def connect(self) -> None:
        """Establish Neo4j connection via Bolt protocol.

        Configuration:
        - Max connection lifetime: 1 hour
        - Connection pool size: 100
        - Acquisition timeout: 60 seconds

        Raises:
            RuntimeError: If connection already established
            Neo4jError: On database connection failure
        """
        if self.driver is not None:
            raise RuntimeError("Connection already established")

        try:
            self.driver = GraphDatabase.driver(
                self.uri,
                auth=(self.username, self.password),
                max_connection_lifetime=3600,  # 1 hour
                max_connection_pool_size=100,
                connection_acquisition_timeout=60,
            )
            # Verify connectivity
            self.driver.verify_connectivity()
            logger.info(
                "Neo4j connection established",
                extra={
                    "uri": self.uri,
                    "database": self.database,
                    "cognitive_trace_id": self.cognitive_trace_id,
                },
            )
        except Neo4jError as e:
            logger.error(
                "Failed to connect to Neo4j",
                extra={
                    "uri": self.uri,
                    "error": str(e),
                    "cognitive_trace_id": self.cognitive_trace_id,
                },
            )
            raise

    def close(self) -> None:
        """Close Neo4j connection and cleanup resources.

        Raises:
            Neo4jError: On connection close failure
        """
        if self.driver:
            try:
                self.driver.close()
                self.driver = None
                logger.info(
                    "Neo4j connection closed",
                    extra={
                        "uri": self.uri,
                        "cognitive_trace_id": self.cognitive_trace_id,
                    },
                )
            except Neo4jError as e:
                logger.error(
                    "Failed to close connection",
                    extra={
                        "error": str(e),
                        "cognitive_trace_id": self.cognitive_trace_id,
                    },
                )
                raise

    def apply(self, payload: bytes | OutboxEntry) -> None:
        """Apply graph operations from K0 outbox entry or raw bytes.

        Payload format (JSON):
        {
            "operation": "create_person" | "create_relationship" | "update_node",
            "params": { ... operation-specific parameters ... }
        }

        Operations:
        - create_person: Create :Person node with properties
        - create_location: Create :Location node
        - create_event: Create :Event node
        - create_organization: Create :Organization node
        - create_thing: Create :Thing node
        - create_relationship: Create relationship between nodes
        - update_node: Update node properties
        - update_relationship: Update relationship properties
        - delete_node: Delete node (cascade deletes relationships)
        - delete_relationship: Delete relationship

        Args:
            payload: Either OutboxEntry object or raw bytes containing JSON payload

        Raises:
            RuntimeError: If connection not established
            ValueError: If operation invalid
            Neo4jError: On query execution failure
        """
        if not self.driver:
            raise RuntimeError("Connection not established")

        try:
            # Handle both OutboxEntry and raw bytes for test compatibility
            payload_bytes = payload.payload if hasattr(payload, "payload") else payload
            data = json.loads(payload_bytes)
            operation = data.get("operation")
            params = data.get("params", {})

            with self.driver.session(database=self.database) as session:
                if operation == "create_person":
                    self._create_person_node(session, params)
                elif operation == "create_location":
                    self._create_location_node(session, params)
                elif operation == "create_event":
                    self._create_event_node(session, params)
                elif operation == "create_organization":
                    self._create_organization_node(session, params)
                elif operation == "create_thing":
                    self._create_thing_node(session, params)
                elif operation == "create_relationship":
                    self._create_relationship(session, params)
                elif operation == "update_node":
                    self._update_node(session, params)
                elif operation == "update_relationship":
                    self._update_relationship(session, params)
                elif operation == "delete_node":
                    self._delete_node(session, params)
                elif operation == "delete_relationship":
                    self._delete_relationship(session, params)
                else:
                    raise ValueError(f"Unknown operation: {operation}")

            logger.debug(
                "Operation applied",
                extra={
                    "operation": operation,
                    "cognitive_trace_id": self.cognitive_trace_id,
                },
            )
        except (json.JSONDecodeError, Neo4jError) as e:
            logger.error(
                "Failed to apply operation",
                extra={
                    "error": str(e),
                    "payload": (
                        str(payload_bytes[:100])
                        if isinstance(payload_bytes, bytes)
                        else str(payload_bytes)[:100]
                    ),
                    "cognitive_trace_id": self.cognitive_trace_id,
                },
            )
            raise

    def _create_person_node(self, session: Session, params: dict[str, Any]) -> None:
        """Create :Person node with temporal properties.

        Args:
            session: Neo4j session
            params: Node parameters (node_id, label, properties, valid_from, valid_to, confidence)
        """
        query = """
        CREATE (p:Person {
            node_id: $node_id,
            label: $label,
            name: $name,
            birthday: $birthday,
            email: $email,
            phone: $phone,
            occupation: $occupation,
            diet: $diet,
            allergies: $allergies,
            privacy_band: $privacy_band,
            valid_from: $valid_from,
            valid_to: $valid_to,
            confidence: $confidence,
            created_at: timestamp(),
            updated_at: timestamp(),
            cognitive_trace_id: $cognitive_trace_id
        })
        RETURN p.node_id AS node_id
        """
        result = session.run(
            query,
            {
                "node_id": params.get("node_id"),
                "label": params.get("label"),
                "name": params.get("name"),
                "birthday": params.get("birthday"),
                "email": params.get("email"),
                "phone": params.get("phone"),
                "occupation": params.get("occupation"),
                "diet": params.get("diet"),
                "allergies": params.get("allergies", []),
                "privacy_band": params.get("privacy_band", "AMBER"),
                "valid_from": params.get("valid_from"),
                "valid_to": params.get("valid_to"),
                "confidence": params.get("confidence", 1.0),
                "cognitive_trace_id": self.cognitive_trace_id,
            },
        )
        record = result.single()
        if record:
            node_id = record["node_id"]
            logger.debug(f"Created :Person node: {node_id}")

    def _create_location_node(self, session: Session, params: dict[str, Any]) -> None:
        """Create :Location node."""
        query = """
        CREATE (l:Location {
            node_id: $node_id,
            label: $label,
            address: $address,
            city: $city,
            state: $state,
            country: $country,
            latitude: $latitude,
            longitude: $longitude,
            privacy_band: $privacy_band,
            created_at: timestamp(),
            updated_at: timestamp(),
            cognitive_trace_id: $cognitive_trace_id
        })
        RETURN l.node_id AS node_id
        """
        result = session.run(
            query,
            {
                "node_id": params.get("node_id"),
                "label": params.get("label"),
                "address": params.get("address"),
                "city": params.get("city"),
                "state": params.get("state"),
                "country": params.get("country"),
                "latitude": params.get("latitude"),
                "longitude": params.get("longitude"),
                "privacy_band": params.get("privacy_band", "GREEN"),
                "cognitive_trace_id": self.cognitive_trace_id,
            },
        )
        record = result.single()
        if record:
            node_id = record["node_id"]
            logger.debug(f"Created :Location node: {node_id}")

    def _create_event_node(self, session: Session, params: dict[str, Any]) -> None:
        """Create :Event node."""
        query = """
        CREATE (e:Event {
            node_id: $node_id,
            label: $label,
            event_type: $event_type,
            event_date: $event_date,
            description: $description,
            participants: $participants,
            privacy_band: $privacy_band,
            created_at: timestamp(),
            updated_at: timestamp(),
            cognitive_trace_id: $cognitive_trace_id
        })
        RETURN e.node_id AS node_id
        """
        result = session.run(
            query,
            {
                "node_id": params.get("node_id"),
                "label": params.get("label"),
                "event_type": params.get("event_type"),
                "event_date": params.get("event_date"),
                "description": params.get("description"),
                "participants": params.get("participants", []),
                "privacy_band": params.get("privacy_band", "AMBER"),
                "cognitive_trace_id": self.cognitive_trace_id,
            },
        )
        record = result.single()
        if record:
            node_id = record["node_id"]
            logger.debug(f"Created :Event node: {node_id}")

    def _create_organization_node(self, session: Session, params: dict[str, Any]) -> None:
        """Create :Organization node."""
        query = """
        CREATE (o:Organization {
            node_id: $node_id,
            label: $label,
            org_type: $org_type,
            industry: $industry,
            website: $website,
            privacy_band: $privacy_band,
            created_at: timestamp(),
            updated_at: timestamp(),
            cognitive_trace_id: $cognitive_trace_id
        })
        RETURN o.node_id AS node_id
        """
        result = session.run(
            query,
            {
                "node_id": params.get("node_id"),
                "label": params.get("label"),
                "org_type": params.get("org_type"),
                "industry": params.get("industry"),
                "website": params.get("website"),
                "privacy_band": params.get("privacy_band", "GREEN"),
                "cognitive_trace_id": self.cognitive_trace_id,
            },
        )
        record = result.single()
        if record:
            node_id = record["node_id"]
            logger.debug(f"Created :Organization node: {node_id}")

    def _create_thing_node(self, session: Session, params: dict[str, Any]) -> None:
        """Create :Thing node."""
        query = """
        CREATE (t:Thing {
            node_id: $node_id,
            label: $label,
            thing_type: $thing_type,
            description: $description,
            privacy_band: $privacy_band,
            created_at: timestamp(),
            updated_at: timestamp(),
            cognitive_trace_id: $cognitive_trace_id
        })
        RETURN t.node_id AS node_id
        """
        result = session.run(
            query,
            {
                "node_id": params.get("node_id"),
                "label": params.get("label"),
                "thing_type": params.get("thing_type"),
                "description": params.get("description"),
                "privacy_band": params.get("privacy_band", "GREEN"),
                "cognitive_trace_id": self.cognitive_trace_id,
            },
        )
        record = result.single()
        if record:
            node_id = record["node_id"]
            logger.debug(f"Created :Thing node: {node_id}")

    def _create_relationship(self, session: Session, params: dict[str, Any]) -> None:
        """Create relationship between nodes with temporal properties.

        Args:
            session: Neo4j session
            params: Relationship parameters (from_id, to_id, rel_type, valid_from, valid_to, confidence)
        """
        rel_type = params.get("rel_type", "RELATED_TO")
        # Dynamic query construction for relationship type (required for Cypher)
        query = f"""
        MATCH (a {{node_id: $from_id}})
        MATCH (b {{node_id: $to_id}})
        CREATE (a)-[r:{rel_type} {{
            edge_id: $edge_id,
            valid_from: $valid_from,
            valid_to: $valid_to,
            confidence: $confidence,
            properties: $properties,
            created_at: timestamp(),
            updated_at: timestamp(),
            cognitive_trace_id: $cognitive_trace_id
        }}]->(b)
        RETURN r
        """
        session.run(
            query,
            {
                "from_id": params.get("from_id"),
                "to_id": params.get("to_id"),
                "edge_id": params.get("edge_id"),
                "valid_from": params.get("valid_from"),
                "valid_to": params.get("valid_to"),
                "confidence": params.get("confidence", 1.0),
                "properties": json.dumps(params.get("properties", {})),
                "cognitive_trace_id": self.cognitive_trace_id,
            },
        )
        logger.debug(f"Created relationship: {rel_type}")

    def _update_node(self, session: Session, params: dict[str, Any]) -> None:
        """Update node properties."""
        query = """
        MATCH (n {node_id: $node_id})
        SET n += $properties
        SET n.updated_at = timestamp()
        RETURN n.node_id AS node_id
        """
        session.run(
            query, {"node_id": params.get("node_id"), "properties": params.get("properties", {})}
        )
        logger.debug(f"Updated node: {params.get('node_id')}")

    def _update_relationship(self, session: Session, params: dict[str, Any]) -> None:
        """Update relationship properties."""
        query = """
        MATCH ()-[r {edge_id: $edge_id}]->()
        SET r += $properties
        SET r.updated_at = timestamp()
        RETURN r.edge_id AS edge_id
        """
        session.run(
            query, {"edge_id": params.get("edge_id"), "properties": params.get("properties", {})}
        )
        logger.debug(f"Updated relationship: {params.get('edge_id')}")

    def _delete_node(self, session: Session, params: dict[str, Any]) -> None:
        """Delete node and all relationships (cascade)."""
        query = """
        MATCH (n {node_id: $node_id})
        DETACH DELETE n
        """
        session.run(query, {"node_id": params.get("node_id")})
        logger.debug(f"Deleted node: {params.get('node_id')}")

    def _delete_relationship(self, session: Session, params: dict[str, Any]) -> None:
        """Delete relationship."""
        query = """
        MATCH ()-[r {edge_id: $edge_id}]->()
        DELETE r
        """
        session.run(query, {"edge_id": params.get("edge_id")})
        logger.debug(f"Deleted relationship: {params.get('edge_id')}")

    def query_relationships(self, node_id: str) -> list[dict[str, Any]]:
        """Query all relationships for a node (for P01 recall).

        Args:
            node_id: Node identifier

        Returns:
            List of relationships with type, target node, properties

        Raises:
            RuntimeError: If connection not established
            Neo4jError: On query execution failure
        """
        if not self.driver:
            raise RuntimeError("Connection not established")

        try:
            with self.driver.session(database=self.database) as session:
                query = """
                MATCH (source {node_id: $node_id})-[r]->(target)
                RETURN
                    type(r) AS rel_type,
                    target,
                    r.valid_from AS valid_from,
                    r.valid_to AS valid_to,
                    r.confidence AS confidence,
                    r.properties AS properties
                """
                result = session.run(query, {"node_id": node_id})
                relationships = []
                for record in result:
                    target_node = dict(record["target"])
                    relationships.append(
                        {
                            "rel_type": record["rel_type"],
                            "target": target_node,
                            "valid_from": record["valid_from"],
                            "valid_to": record["valid_to"],
                            "confidence": record["confidence"],
                            "properties": (
                                json.loads(record["properties"]) if record["properties"] else {}
                            ),
                        }
                    )
                logger.debug(
                    "Relationships queried",
                    extra={
                        "node_id": node_id,
                        "count": len(relationships),
                        "cognitive_trace_id": self.cognitive_trace_id,
                    },
                )
                return relationships
        except Neo4jError as e:
            logger.error(
                "Failed to query relationships",
                extra={
                    "node_id": node_id,
                    "error": str(e),
                    "cognitive_trace_id": self.cognitive_trace_id,
                },
            )
            raise

    def find_path(
        self, source_id: str, target_id: str, max_depth: int = 6, rel_types: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """Find shortest path between two nodes (BFS).

        Args:
            source_id: Source node ID
            target_id: Target node ID
            max_depth: Maximum path depth (default 6)
            rel_types: Optional relationship type filter

        Returns:
            List of paths (each path is list of nodes and relationships)

        Raises:
            RuntimeError: If connection not established
            Neo4jError: On query execution failure
        """
        if not self.driver:
            raise RuntimeError("Connection not established")

        try:
            with self.driver.session(database=self.database) as session:
                rel_filter = ""
                if rel_types:
                    rel_filter = f":{':'.join(rel_types)}"

                # Dynamic query construction for relationship types (required for Cypher)
                query = f"""
                MATCH path = shortestPath(
                    (source {{node_id: $source_id}})-[{rel_filter}*1..{max_depth}]->(target {{node_id: $target_id}})
                )
                RETURN path
                LIMIT 5
                """
                result = session.run(query, {"source_id": source_id, "target_id": target_id})
                paths = []
                for record in result:
                    path_data = record["path"]
                    paths.append(
                        {
                            "nodes": [dict(node) for node in path_data.nodes],
                            "relationships": [
                                {"type": rel.type, "properties": dict(rel)}
                                for rel in path_data.relationships
                            ],
                        }
                    )
                logger.debug(
                    "Paths found",
                    extra={
                        "source_id": source_id,
                        "target_id": target_id,
                        "count": len(paths),
                        "cognitive_trace_id": self.cognitive_trace_id,
                    },
                )
                return paths
        except Neo4jError as e:
            logger.error(
                "Failed to find path",
                extra={
                    "source_id": source_id,
                    "target_id": target_id,
                    "error": str(e),
                    "cognitive_trace_id": self.cognitive_trace_id,
                },
            )
            raise

    def __enter__(self) -> "Neo4jKGDriver":
        """Context manager entry: connect to Neo4j."""
        self.connect()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit: close connection."""
        self.close()


# Factory function for outbox worker compatibility
def build_driver() -> Neo4jKGDriver:
    """Factory function to create Neo4jKGDriver instance.

    Returns a Neo4jKGDriver with default configuration for outbox processing.
    Uses environment variables for connection settings.

    Returns:
        Neo4jKGDriver: Configured driver instance
    """
    import os

    uri = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
    username = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "test-password")
    database = os.getenv("NEO4J_DATABASE", "neo4j")

    return Neo4jKGDriver(
        uri=uri,
        username=username,
        password=password,
        database=database,
    )
