// Neo4j Schema Initialization - Constraints
// Related: ADR-0081a (Temporal Graph Schema Design)
// Purpose: Create uniqueness constraints and indexes for optimal query performance
// Run: Automatically on Neo4j startup via init scripts

// =============================================================================
// UNIQUENESS CONSTRAINTS (Ensure node_id uniqueness per label)
// =============================================================================

// Person nodes - Unique by node_id
CREATE CONSTRAINT person_node_id_unique IF NOT EXISTS
FOR (p:Person) REQUIRE p.node_id IS UNIQUE;

// Location nodes - Unique by node_id
CREATE CONSTRAINT location_node_id_unique IF NOT EXISTS
FOR (l:Location) REQUIRE l.node_id IS UNIQUE;

// Event nodes - Unique by node_id
CREATE CONSTRAINT event_node_id_unique IF NOT EXISTS
FOR (e:Event) REQUIRE e.node_id IS UNIQUE;

// Organization nodes - Unique by node_id
CREATE CONSTRAINT organization_node_id_unique IF NOT EXISTS
FOR (o:Organization) REQUIRE o.node_id IS UNIQUE;

// Thing nodes - Unique by node_id
CREATE CONSTRAINT thing_node_id_unique IF NOT EXISTS
FOR (t:Thing) REQUIRE t.node_id IS UNIQUE;

// =============================================================================
// EXISTENCE CONSTRAINTS (Ensure required properties exist)
// =============================================================================

// All nodes must have created_at timestamp
CREATE CONSTRAINT person_created_at_exists IF NOT EXISTS
FOR (p:Person) REQUIRE p.created_at IS NOT NULL;

CREATE CONSTRAINT location_created_at_exists IF NOT EXISTS
FOR (l:Location) REQUIRE l.created_at IS NOT NULL;

CREATE CONSTRAINT event_created_at_exists IF NOT EXISTS
FOR (e:Event) REQUIRE e.created_at IS NOT NULL;

CREATE CONSTRAINT organization_created_at_exists IF NOT EXISTS
FOR (o:Organization) REQUIRE o.created_at IS NOT NULL;

CREATE CONSTRAINT thing_created_at_exists IF NOT EXISTS
FOR (t:Thing) REQUIRE t.created_at IS NOT NULL;

// All nodes must have label (human-readable name)
CREATE CONSTRAINT person_label_exists IF NOT EXISTS
FOR (p:Person) REQUIRE p.label IS NOT NULL;

CREATE CONSTRAINT location_label_exists IF NOT EXISTS
FOR (l:Location) REQUIRE l.label IS NOT NULL;

CREATE CONSTRAINT event_label_exists IF NOT EXISTS
FOR (e:Event) REQUIRE e.label IS NOT NULL;

CREATE CONSTRAINT organization_label_exists IF NOT EXISTS
FOR (o:Organization) REQUIRE o.label IS NOT NULL;

CREATE CONSTRAINT thing_label_exists IF NOT EXISTS
FOR (t:Thing) REQUIRE t.label IS NOT NULL;
