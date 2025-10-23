"""
K1 L4 Ingress — API Gateway (REST)

**Purpose:** REST API with JSON/FlatBuffers dual format, JWT auth, cursor-based pagination, OpenAPI 3.1

**Components:**
- content_negotiation/ — Accept/Content-Type header parsing, JSON/FlatBuffers selection
- openapi/ — OpenAPI 3.1 spec generation from FlatBuffers schemas
- serialization/ — JSON↔FlatBuffers conversion <5ms
- sessions/ — Session CRUD (POST/GET/PATCH/DELETE)
- pagination/ — Cursor-based pagination <100ms P95
- auth/ — JWT validation <2ms P95

**Performance:**
- REST endpoint: <100ms P95
- JWT validation: <2ms P95
- Pagination: <100ms P95
- Serialization: <5ms overhead

**ADRs (13 total):** ADR-0014 to 0014d (REST API), ADR-0041 to 0041d (Session Management),
ADR-0023 to 0023c (Pagination), ADR-0037 to 0037d (JWT Auth), ADR-0047 (OpenAPI)

**Last Updated:** October 2025
"""

__version__ = "0.1.0"

# TODO: Implement content_negotiation/, openapi/, serialization/, sessions/, pagination/, auth/
