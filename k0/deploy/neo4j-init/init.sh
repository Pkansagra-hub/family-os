#!/bin/bash
# Neo4j Schema Initialization Script
# Purpose: Apply constraints and indexes to Neo4j database on first startup
# Related: ADR-0081a (Temporal Graph Schema Design)

set -e

echo "[neo4j-init] Waiting for Neo4j to be ready..."

# Wait for Neo4j to be fully available (up to 60 seconds)
until cypher-shell -u neo4j -p "${NEO4J_PASSWORD:-test-password}" "RETURN 1;" > /dev/null 2>&1; do
  echo "[neo4j-init] Neo4j not ready yet, waiting..."
  sleep 2
done

echo "[neo4j-init] Neo4j is ready. Applying schema..."

# Apply constraints
echo "[neo4j-init] Creating uniqueness constraints..."
cypher-shell -u neo4j -p "${NEO4J_PASSWORD:-test-password}" < /docker-entrypoint-initdb.d/001_constraints.cypher

# Apply indexes
echo "[neo4j-init] Creating indexes..."
cypher-shell -u neo4j -p "${NEO4J_PASSWORD:-test-password}" < /docker-entrypoint-initdb.d/002_indexes.cypher

echo "[neo4j-init] Schema initialization complete!"
