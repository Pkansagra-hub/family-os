// Neo4j Baseline Schema Migration
// Version: 0001
// Related: ADR-0081a (Temporal Graph Schema Design)
// Purpose: Create constraints and indexes for K0 knowledge graph
// Performance Targets: <10ms P95 entity lookup, <30ms P95 relationship query
// Note: Existence constraints require Enterprise Edition, using uniqueness only

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
// NODE PROPERTY INDEXES (for fast lookups)
// =============================================================================

// Person indexes
CREATE INDEX person_name_idx IF NOT EXISTS FOR (p:Person) ON (p.name);
CREATE INDEX person_email_idx IF NOT EXISTS FOR (p:Person) ON (p.email);
CREATE INDEX person_privacy_band_idx IF NOT EXISTS FOR (p:Person) ON (p.privacy_band);
CREATE INDEX person_updated_at_idx IF NOT EXISTS FOR (p:Person) ON (p.updated_at);
CREATE INDEX person_created_at_idx IF NOT EXISTS FOR (p:Person) ON (p.created_at);
CREATE INDEX person_label_idx IF NOT EXISTS FOR (p:Person) ON (p.label);

// Location indexes
CREATE INDEX location_address_idx IF NOT EXISTS FOR (l:Location) ON (l.address);
CREATE INDEX location_city_idx IF NOT EXISTS FOR (l:Location) ON (l.city);
CREATE INDEX location_coordinates_idx IF NOT EXISTS FOR (l:Location) ON (l.latitude, l.longitude);
CREATE INDEX location_created_at_idx IF NOT EXISTS FOR (l:Location) ON (l.created_at);
CREATE INDEX location_label_idx IF NOT EXISTS FOR (l:Location) ON (l.label);

// Event indexes
CREATE INDEX event_type_idx IF NOT EXISTS FOR (e:Event) ON (e.event_type);
CREATE INDEX event_date_idx IF NOT EXISTS FOR (e:Event) ON (e.event_date);
CREATE INDEX event_created_at_idx IF NOT EXISTS FOR (e:Event) ON (e.created_at);
CREATE INDEX event_label_idx IF NOT EXISTS FOR (e:Event) ON (e.label);

// Organization indexes
CREATE INDEX organization_type_idx IF NOT EXISTS FOR (o:Organization) ON (o.org_type);
CREATE INDEX organization_industry_idx IF NOT EXISTS FOR (o:Organization) ON (o.industry);
CREATE INDEX organization_created_at_idx IF NOT EXISTS FOR (o:Organization) ON (o.created_at);
CREATE INDEX organization_label_idx IF NOT EXISTS FOR (o:Organization) ON (o.label);

// Thing indexes
CREATE INDEX thing_type_idx IF NOT EXISTS FOR (t:Thing) ON (t.thing_type);
CREATE INDEX thing_created_at_idx IF NOT EXISTS FOR (t:Thing) ON (t.created_at);
CREATE INDEX thing_label_idx IF NOT EXISTS FOR (t:Thing) ON (t.label);

// =============================================================================
// TEMPORAL PROPERTY INDEXES (for time-based queries)
// =============================================================================

// Valid_from/valid_to indexes for all node types (temporal validity)
CREATE INDEX person_valid_from_idx IF NOT EXISTS FOR (p:Person) ON (p.valid_from);
CREATE INDEX person_valid_to_idx IF NOT EXISTS FOR (p:Person) ON (p.valid_to);

CREATE INDEX location_valid_from_idx IF NOT EXISTS FOR (l:Location) ON (l.valid_from);
CREATE INDEX location_valid_to_idx IF NOT EXISTS FOR (l:Location) ON (l.valid_to);

CREATE INDEX event_valid_from_idx IF NOT EXISTS FOR (e:Event) ON (e.valid_from);
CREATE INDEX event_valid_to_idx IF NOT EXISTS FOR (e:Event) ON (e.valid_to);

CREATE INDEX organization_valid_from_idx IF NOT EXISTS FOR (o:Organization) ON (o.valid_from);
CREATE INDEX organization_valid_to_idx IF NOT EXISTS FOR (o:Organization) ON (o.valid_to);

// =============================================================================
// COGNITIVE TRACE INDEXES (for observability)
// =============================================================================

// Cognitive trace ID for all nodes (K0 observability integration)
CREATE INDEX person_cognitive_trace_idx IF NOT EXISTS FOR (p:Person) ON (p.cognitive_trace_id);
CREATE INDEX location_cognitive_trace_idx IF NOT EXISTS FOR (l:Location) ON (l.cognitive_trace_id);
CREATE INDEX event_cognitive_trace_idx IF NOT EXISTS FOR (e:Event) ON (e.cognitive_trace_id);
CREATE INDEX organization_cognitive_trace_idx IF NOT EXISTS FOR (o:Organization) ON (o.cognitive_trace_id);
CREATE INDEX thing_cognitive_trace_idx IF NOT EXISTS FOR (t:Thing) ON (t.cognitive_trace_id);

// =============================================================================
// FULL-TEXT INDEXES (for semantic search)
// =============================================================================

// Person full-text search (name, occupation, bio)
CREATE FULLTEXT INDEX person_fulltext_idx IF NOT EXISTS
FOR (p:Person) ON EACH [p.name, p.label, p.occupation];

// Location full-text search (address, city, description)
CREATE FULLTEXT INDEX location_fulltext_idx IF NOT EXISTS
FOR (l:Location) ON EACH [l.label, l.address, l.city];

// Event full-text search (label, description, type)
CREATE FULLTEXT INDEX event_fulltext_idx IF NOT EXISTS
FOR (e:Event) ON EACH [e.label, e.description, e.event_type];

// Organization full-text search (name, industry)
CREATE FULLTEXT INDEX organization_fulltext_idx IF NOT EXISTS
FOR (o:Organization) ON EACH [o.label, o.industry];
