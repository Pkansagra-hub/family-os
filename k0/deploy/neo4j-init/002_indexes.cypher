// Neo4j Schema Initialization - Indexes
// Related: ADR-0081a (Temporal Graph Schema Design)
// Purpose: Create indexes for query performance optimization
// Performance Targets: <10ms P95 entity lookup, <30ms P95 relationship query

// =============================================================================
// NODE PROPERTY INDEXES (for fast lookups)
// =============================================================================

// Person indexes
CREATE INDEX person_name_idx IF NOT EXISTS FOR (p:Person) ON (p.name);
CREATE INDEX person_email_idx IF NOT EXISTS FOR (p:Person) ON (p.email);
CREATE INDEX person_privacy_band_idx IF NOT EXISTS FOR (p:Person) ON (p.privacy_band);
CREATE INDEX person_updated_at_idx IF NOT EXISTS FOR (p:Person) ON (p.updated_at);

// Location indexes
CREATE INDEX location_address_idx IF NOT EXISTS FOR (l:Location) ON (l.address);
CREATE INDEX location_city_idx IF NOT EXISTS FOR (l:Location) ON (l.city);
CREATE INDEX location_coordinates_idx IF NOT EXISTS FOR (l:Location) ON (l.latitude, l.longitude);

// Event indexes
CREATE INDEX event_type_idx IF NOT EXISTS FOR (e:Event) ON (e.event_type);
CREATE INDEX event_date_idx IF NOT EXISTS FOR (e:Event) ON (e.event_date);

// Organization indexes
CREATE INDEX organization_type_idx IF NOT EXISTS FOR (o:Organization) ON (o.org_type);
CREATE INDEX organization_industry_idx IF NOT EXISTS FOR (o:Organization) ON (o.industry);

// Thing indexes
CREATE INDEX thing_type_idx IF NOT EXISTS FOR (t:Thing) ON (t.thing_type);

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
