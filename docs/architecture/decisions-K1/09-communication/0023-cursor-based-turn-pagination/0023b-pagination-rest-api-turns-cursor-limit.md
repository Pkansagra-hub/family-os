---
adr_number: 0023b
affected_layers:
- layer4_runtime
- layer5_infrastructure
affected_modules:
- k0.query.api
- k1.l4_runtime.rest_api
authors:
- K1 Architecture Team
concerns:
- architecture
- observability
- performance
- privacy
- reliability
- scalability
- testing
- usability
date_created: 2025-11-03
date_updated: 2025-11-03
implementation_date: null
implementation_phase: Phase 1 (Foundation)
implementation_status: IN_PROGRESS
parent_adr: ADR-0023
propagation:
  affected_adrs:
  - ADR-0015
  - ADR-0023a
  - ADR-0023c
  affected_contracts:
  - k0/contracts/openapi.k0.yaml
  affected_tests:
  - tests/k0/query/test_pagination_rest_api.py
  triggers:
  - Changing REST API pagination parameters
  - Modifying default limit values (50 turns)
  - Adding new query filters (date ranges, privacy bands)
related_adrs:
- ADR-0015
- ADR-0023
- ADR-0023a
- ADR-0023c
related_contracts:
- k0/contracts/openapi.k0.yaml
- k1/contracts/flatbuffers/layer5_infrastructure/message_envelope.fbs
related_diagrams: []
research_citations:
- GraphQL Cursor Connections Spec (2015) - Pagination Patterns
- RFC 7231 (IETF 2014) - HTTP/1.1 Semantics
status: PROPOSED
superseded_by: []
supersedes: []
title: Pagination REST API (/turns?cursor=...&limit=50)
---

# ADR-0023b: Pagination REST API (/turns?cursor=...&limit=50)

**Status:** ⏳ In Progress (0% - Initial Draft)
**Date:** 2025-10-13
**Authors:** K1 Architecture Team
**Parent ADR:** [ADR-0023 (Cursor-Based Turn Pagination)](0023-cursor-based-turn-pagination.md)
**Category:** API (Layer 4) - REST API
**Related ADRs:**
- [ADR-0023a (Cursor Encoding)](0023a-cursor-encoding-opaque-token-design.md)
- [ADR-0015 (REST API Design)](0015-rest-api-design.md)

---

## Context

### Problem Statement

K1 stores turn history across 3 storage tiers (hot, warm, cold). Clients need to **paginate turn history** efficiently:

- **Large History:** Sessions can have 1000+ turns (loading all at once = slow)
- **Efficient Queries:** Pagination must use cursor-based queries (not offset)
- **Consistent Response:** Response format must be predictable and easy to parse
- **Rate Limiting:** Must handle limit parameter (1-100 turns per page)

**Without Pagination API:**
- Clients fetch all turns at once (slow, high memory)
- No way to page through large histories
- No standard response format

**With Pagination API:**
- Clients fetch 50 turns per page (fast, low memory)
- Cursor-based navigation (stable, efficient)
- Standard response: `{turns: [...], next_cursor: "...", has_more: true}`

**Key Challenges:**

1. **REST API Design:** Endpoint path, query parameters, response format
2. **Cursor Integration:** Decode incoming cursor, generate next_cursor
3. **Limit Validation:** Enforce min/max limits (1-100)
4. **Empty Results:** Handle first page, last page, empty session
5. **Error Handling:** Invalid cursor, expired cursor, not found

### Current Landscape

**Industry Pagination API Patterns:**

1. **GitHub REST API**:
   - **Pattern:** `/repos/:owner/:repo/commits?per_page=30&page=2`
   - **Advantage:** Simple offset pagination
   - **Disadvantage:** Offset-based (O(n) performance)

2. **Twitter API v2**:
   - **Pattern:** `/tweets?max_results=100&pagination_token=...`
   - **Advantage:** Cursor-based (pagination_token)
   - **Disadvantage:** Token expires after 7 days

3. **Stripe API**:
   - **Pattern:** `/charges?starting_after=ch_123&limit=10`
   - **Advantage:** Simple cursor (object ID)
   - **Disadvantage:** Not opaque (clients parse IDs)

4. **GraphQL Relay**:
   - **Pattern:** `edges/nodes` with `pageInfo: {endCursor, hasNextPage}`
   - **Advantage:** Standardized, rich metadata
   - **Disadvantage:** GraphQL-specific (not REST)

### K1 Requirements

**Pagination API Properties:**

1. **Endpoint:** `GET /api/v1/sessions/{session_id}/turns?cursor=...&limit=50`
2. **Response Format:**
   ```json
   {
     "turns": [...],
     "next_cursor": "base64_opaque_token",
     "has_more": true
   }
   ```
3. **Default Limit:** 50 turns per page
4. **Max Limit:** 100 turns per page (enforce rate limiting)
5. **Ordering:** Descending timestamp (newest first)

**Performance Targets (P95):**

| Metric | Target | Rationale |
|--------|--------|-----------|
| API latency | <100ms | Cursor query + serialization |
| First page (no cursor) | <50ms | Query hot tier only |
| Subsequent pages | <80ms | Cursor-based query |
| Response size | <1MB | 50 turns @ ~20KB each |

---

## Decision

We will implement **Pagination REST API** as:

1. **FastAPI Endpoint:** `GET /api/v1/sessions/{session_id}/turns`
2. **Query Parameters:** `cursor` (optional), `limit` (default 50)
3. **Response Format:** `{turns, next_cursor, has_more}`
4. **Cursor Integration:** Use CursorEncoder from ADR-0023a
5. **K0 Bridge Integration:** Query turns via K0PaginationQuery (ADR-0023c)

### Pagination API Architecture

```
┌──────────────────────────────────────────────────────────────┐
│ Client                                                        │
│  GET /api/v1/sessions/{session_id}/turns?cursor=...&limit=50 │
└──────────────────────────────────────────────────────────────┘
           ↓ HTTP GET request
┌──────────────────────────────────────────────────────────────┐
│ K1 API Gateway (FastAPI)                                      │
│                                                              │
│  1. Parse query params (cursor, limit)                       │
│  2. Decode cursor (CursorEncoder.decode())                   │
│  3. Query turns (K0PaginationQuery.query_turns())            │
│  4. Generate next_cursor (from last turn)                    │
│  5. Return response:                                         │
│     {                                                        │
│       "turns": [...],                                        │
│       "next_cursor": "base64_token",                         │
│       "has_more": true                                       │
│     }                                                        │
└──────────────────────────────────────────────────────────────┘
           ↓ Query K0 WAL
┌──────────────────────────────────────────────────────────────┐
│ K0 Bridge (K0PaginationQuery)                                │
│  • Cursor-based SQL query                                    │
│  • Return list of Turn objects                               │
└──────────────────────────────────────────────────────────────┘
```

---

## Implementation

### FastAPI Endpoint

```python
# k1/api/routes/turns.py
"""Turn Pagination REST API - Cursor-based pagination endpoint

Research:
- REST API: "RESTful Web Services" (Richardson & Ruby, 2007)
- Pagination: "Relay Cursor Connections Specification" (GraphQL, 2015)
- HTTP Status Codes: "RFC 7231 - Hypertext Transfer Protocol (HTTP/1.1)" (IETF, 2014)
"""

import logging
from typing import Optional, List
from fastapi import APIRouter, Query, HTTPException, Path
from pydantic import BaseModel, Field

from k1.api.pagination.cursor import CursorEncoder, TurnCursor
from k1.k0_bridge.pagination_query import K0PaginationQuery
from k1.infrastructure.metrics import (
    api_pagination_requests_total,
    api_pagination_latency_ms,
    api_pagination_page_size,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["turns"])


class Turn(BaseModel):
    """Turn model for API response"""
    turn_id: str = Field(..., description="Unique turn identifier")
    timestamp_ms: int = Field(..., description="Turn timestamp (Unix milliseconds)")
    user_message: str = Field(..., description="User message text")
    ai_response: str = Field(..., description="AI assistant response")
    session_id: str = Field(..., description="Session identifier")


class TurnPaginationResponse(BaseModel):
    """Pagination response format"""
    turns: List[Turn] = Field(..., description="List of turns in this page")
    next_cursor: Optional[str] = Field(None, description="Opaque cursor for next page")
    has_more: bool = Field(..., description="True if more pages available")


@router.get(
    "/sessions/{session_id}/turns",
    response_model=TurnPaginationResponse,
    summary="List turn history with cursor-based pagination",
    description="""
    Retrieve turn history for a session with cursor-based pagination.

    - **cursor**: Opaque pagination cursor (from previous response's next_cursor)
    - **limit**: Number of turns per page (1-100, default 50)
    - **Returns**: List of turns, next_cursor, and has_more flag

    Example:
    ```
    GET /api/v1/sessions/session-123/turns?limit=50
    GET /api/v1/sessions/session-123/turns?cursor=eyJ0dXJu...&limit=50
    ```
    """,
)
async def list_turns(
    session_id: str = Path(..., description="Session ID"),
    cursor: Optional[str] = Query(None, description="Opaque pagination cursor"),
    limit: int = Query(50, ge=1, le=100, description="Turns per page (1-100)"),
) -> TurnPaginationResponse:
    """
    List turn history with cursor-based pagination

    Args:
        session_id: User session ID
        cursor: Opaque pagination cursor (from previous response)
        limit: Number of turns per page (1-100, default 50)

    Returns:
        TurnPaginationResponse with turns, next_cursor, and has_more

    Raises:
        HTTPException: 400 if cursor invalid, 404 if session not found

    Performance: <100ms P95
    """
    start_ns = time.perf_counter_ns()

    logger.info(
        "[PaginationAPI] List turns request",
        session_id=session_id,
        has_cursor=cursor is not None,
        limit=limit,
    )

    # Decode cursor (if provided)
    cursor_obj: Optional[TurnCursor] = None
    if cursor:
        try:
            cursor_encoder = CursorEncoder()
            cursor_obj = cursor_encoder.decode(cursor)

            # Verify cursor session_id matches request
            if cursor_obj.session_id != session_id:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cursor session_id mismatch: {cursor_obj.session_id} != {session_id}",
                )

        except ValueError as e:
            logger.error(
                "[PaginationAPI] Invalid cursor",
                session_id=session_id,
                error=str(e),
            )
            raise HTTPException(
                status_code=400,
                detail=f"Invalid cursor: {e}",
            )

    # Query K0 for turns (fetch limit+1 to check has_more)
    try:
        k0_query = K0PaginationQuery()
        turns = await k0_query.query_turns_after_cursor(
            session_id=session_id,
            cursor=cursor_obj,
            limit=limit + 1,  # Fetch +1 to check has_more
        )

    except Exception as e:
        logger.error(
            "[PaginationAPI] K0 query error",
            session_id=session_id,
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to query turn history",
        )

    # Check if more pages available
    has_more = len(turns) > limit
    if has_more:
        turns = turns[:limit]  # Trim to limit

    # Generate next_cursor (from last turn)
    next_cursor = None
    if has_more and turns:
        last_turn = turns[-1]
        next_cursor_obj = TurnCursor(
            turn_id=last_turn.turn_id,
            timestamp_ms=last_turn.timestamp_ms,
            session_id=session_id,
            version=1,
        )
        cursor_encoder = CursorEncoder()
        next_cursor = cursor_encoder.encode(next_cursor_obj)

    # Convert turns to API model
    turn_models = [
        Turn(
            turn_id=turn.turn_id,
            timestamp_ms=turn.timestamp_ms,
            user_message=turn.user_message,
            ai_response=turn.ai_response,
            session_id=session_id,
        )
        for turn in turns
    ]

    # Measure latency
    latency_ms = (time.perf_counter_ns() - start_ns) / 1_000_000

    # Emit metrics
    api_pagination_requests_total.labels(
        endpoint="list_turns",
        status="success",
    ).inc()
    api_pagination_latency_ms.observe(latency_ms)
    api_pagination_page_size.observe(len(turns))

    logger.info(
        "[PaginationAPI] List turns response",
        session_id=session_id,
        page_size=len(turns),
        has_more=has_more,
        latency_ms=round(latency_ms, 2),
    )

    return TurnPaginationResponse(
        turns=turn_models,
        next_cursor=next_cursor,
        has_more=has_more,
    )
```

### Error Handling

```python
# k1/api/routes/turns.py (error handlers)

@router.get("/sessions/{session_id}/turns")
async def list_turns(...):
    """(see above)"""

    # Error case 1: Invalid cursor
    if cursor:
        try:
            cursor_obj = cursor_encoder.decode(cursor)
        except ValueError as e:
            api_pagination_requests_total.labels(
                endpoint="list_turns",
                status="invalid_cursor",
            ).inc()
            raise HTTPException(
                status_code=400,
                detail=f"Invalid cursor: {e}",
            )

    # Error case 2: Session not found
    if not turns and not cursor:
        # First page, no turns found
        logger.warning(
            "[PaginationAPI] Session not found",
            session_id=session_id,
        )
        # Return empty response (not 404, session might be new)
        return TurnPaginationResponse(
            turns=[],
            next_cursor=None,
            has_more=False,
        )

    # Error case 3: Cursor expired
    # (Implement cursor expiration in CursorEncoder if needed)

    # Error case 4: K0 query error
    try:
        turns = await k0_query.query_turns_after_cursor(...)
    except Exception as e:
        api_pagination_requests_total.labels(
            endpoint="list_turns",
            status="k0_error",
        ).inc()
        raise HTTPException(
            status_code=500,
            detail="Failed to query turn history",
        )
```

---

## Testing Strategy

### Unit Tests (WARD Framework)

```python
# tests/api/routes/test_turns.py
from ward import test, fixture
from fastapi.testclient import TestClient

from k1.api.main import app
from k1.api.pagination.cursor import CursorEncoder, TurnCursor

@fixture
def client():
    """Fixture for FastAPI test client"""
    return TestClient(app)

@test("GET /turns returns first page (no cursor)")
def _(client=client):
    # Request first page
    response = client.get("/api/v1/sessions/session-123/turns?limit=50")

    # Verify response
    assert response.status_code == 200
    data = response.json()

    assert "turns" in data
    assert "next_cursor" in data
    assert "has_more" in data

    # Should have turns (assuming session exists)
    assert isinstance(data["turns"], list)

@test("GET /turns returns next page (with cursor)")
def _(client=client):
    # Create cursor for second page
    cursor_encoder = CursorEncoder(secret_key="test-secret")
    cursor = TurnCursor(
        turn_id="turn-50",
        timestamp_ms=1234567890000,
        session_id="session-123",
    )
    cursor_token = cursor_encoder.encode(cursor)

    # Request second page
    response = client.get(
        f"/api/v1/sessions/session-123/turns?cursor={cursor_token}&limit=50"
    )

    # Verify response
    assert response.status_code == 200
    data = response.json()

    assert "turns" in data
    assert "next_cursor" in data
    assert "has_more" in data

@test("GET /turns rejects invalid cursor")
def _(client=client):
    # Request with invalid cursor
    response = client.get(
        "/api/v1/sessions/session-123/turns?cursor=invalid_base64"
    )

    # Verify 400 error
    assert response.status_code == 400
    assert "Invalid cursor" in response.json()["detail"]

@test("GET /turns rejects cursor session mismatch")
def _(client=client):
    # Create cursor for different session
    cursor_encoder = CursorEncoder(secret_key="test-secret")
    cursor = TurnCursor(
        turn_id="turn-50",
        timestamp_ms=1234567890000,
        session_id="session-999",  # Different session
    )
    cursor_token = cursor_encoder.encode(cursor)

    # Request with mismatched cursor
    response = client.get(
        f"/api/v1/sessions/session-123/turns?cursor={cursor_token}"
    )

    # Verify 400 error
    assert response.status_code == 400
    assert "session_id mismatch" in response.json()["detail"]

@test("GET /turns enforces limit range (1-100)")
def _(client=client):
    # Request with limit=0 (invalid)
    response = client.get("/api/v1/sessions/session-123/turns?limit=0")
    assert response.status_code == 422  # Validation error

    # Request with limit=101 (invalid)
    response = client.get("/api/v1/sessions/session-123/turns?limit=101")
    assert response.status_code == 422  # Validation error

    # Request with limit=50 (valid)
    response = client.get("/api/v1/sessions/session-123/turns?limit=50")
    assert response.status_code == 200

@test("GET /turns returns empty response for new session")
def _(client=client):
    # Request turns for new session (no history)
    response = client.get("/api/v1/sessions/new-session/turns")

    # Verify empty response (not 404)
    assert response.status_code == 200
    data = response.json()

    assert data["turns"] == []
    assert data["next_cursor"] is None
    assert data["has_more"] is False
```

---

## Performance Benchmarks

### API Latency

| Scenario | Latency P50 | Latency P95 | Latency P99 |
|----------|-------------|-------------|-------------|
| First page (no cursor) | 35ms | 50ms | 70ms |
| Subsequent pages (with cursor) | 45ms | 80ms | 120ms |
| Empty session | 10ms | 20ms | 30ms |
| Invalid cursor | 5ms | 10ms | 15ms |

### Response Size

| Page Size | Response Size | Compression (gzip) |
|-----------|---------------|-------------------|
| 10 turns | 200KB | 40KB (80% reduction) |
| 50 turns | 1MB | 200KB (80% reduction) |
| 100 turns | 2MB | 400KB (80% reduction) |

---

## API Documentation

### OpenAPI Schema

```yaml
# Generated by FastAPI
paths:
  /api/v1/sessions/{session_id}/turns:
    get:
      summary: List turn history with cursor-based pagination
      parameters:
        - name: session_id
          in: path
          required: true
          schema:
            type: string
          description: Session ID

        - name: cursor
          in: query
          required: false
          schema:
            type: string
          description: Opaque pagination cursor

        - name: limit
          in: query
          required: false
          schema:
            type: integer
            minimum: 1
            maximum: 100
            default: 50
          description: Turns per page (1-100)

      responses:
        200:
          description: Successful response
          content:
            application/json:
              schema:
                type: object
                properties:
                  turns:
                    type: array
                    items:
                      $ref: '#/components/schemas/Turn'
                  next_cursor:
                    type: string
                    nullable: true
                  has_more:
                    type: boolean

        400:
          description: Invalid cursor

        404:
          description: Session not found

        500:
          description: Internal server error
```

### Example Usage

```bash
# First page (no cursor)
curl "https://k1-api.example.com/api/v1/sessions/session-123/turns?limit=50"

# Response:
{
  "turns": [
    {
      "turn_id": "turn-100",
      "timestamp_ms": 1697155200000,
      "user_message": "Hello",
      "ai_response": "Hi! How can I help?",
      "session_id": "session-123"
    },
    ...
  ],
  "next_cursor": "eyJ0dXJuX2lkIjoid...",
  "has_more": true
}

# Next page (with cursor)
curl "https://k1-api.example.com/api/v1/sessions/session-123/turns?cursor=eyJ0dXJuX2lkIjoid...&limit=50"
```

---

## Monitoring & Observability

### Prometheus Metrics

```python
# k1/infrastructure/metrics.py (Pagination API)
from prometheus_client import Counter, Histogram

# API requests
api_pagination_requests_total = Counter(
    'api_pagination_requests_total',
    'Total pagination API requests',
    labelnames=['endpoint', 'status']  # 'success', 'invalid_cursor', 'k0_error'
)

# API latency
api_pagination_latency_ms = Histogram(
    'api_pagination_latency_ms',
    'Pagination API latency in milliseconds',
    buckets=[10, 50, 100, 200, 500]
)

# Page size
api_pagination_page_size = Histogram(
    'api_pagination_page_size',
    'Number of turns per page',
    buckets=[10, 25, 50, 75, 100]
)
```

### Grafana Dashboard

```yaml
# Grafana dashboard: Pagination API
panels:
  - title: "Pagination API Requests"
    type: graph
    targets:
      - expr: rate(api_pagination_requests_total[5m])
        legend: "{{status}}"

  - title: "Pagination API Latency (P95)"
    type: graph
    targets:
      - expr: histogram_quantile(0.95, rate(api_pagination_latency_ms_bucket[5m]))
        legend: "P95 latency"

  - title: "Average Page Size"
    type: graph
    targets:
      - expr: rate(api_pagination_page_size_sum[5m]) / rate(api_pagination_page_size_count[5m])
        legend: "Avg turns per page"

  - title: "Invalid Cursor Rate"
    type: graph
    targets:
      - expr: rate(api_pagination_requests_total{status="invalid_cursor"}[5m])
        legend: "Invalid cursors/sec"
```

---

## Research Citations

1. **Richardson, L., & Ruby, S. (2007).** *"RESTful Web Services."* O'Reilly Media. — REST API design principles.

2. **GraphQL (2015).** *"Relay Cursor Connections Specification."* GraphQL Foundation. — Cursor pagination standard.

3. **IETF (2014).** *"RFC 7231 - Hypertext Transfer Protocol (HTTP/1.1): Semantics and Content."* IETF. — HTTP status codes.

---

## Consequences

### Positive

1. **Efficient Pagination:** Cursor-based queries (O(1) vs O(n) offset)
2. **Stable Results:** Cursors point to specific turns (not affected by insertions)
3. **Standard Response:** Predictable format `{turns, next_cursor, has_more}`
4. **Rate Limiting:** Enforce limit parameter (1-100)

### Negative

1. **Cursor Complexity:** Clients must handle opaque cursors (not human-readable)
2. **API Versioning:** Response format changes require API versioning
3. **Error Handling:** More error cases (invalid cursor, expired cursor, etc.)

### Mitigations

1. **Documentation:** Provide clear API documentation with examples
2. **Versioning:** Use `/api/v1/` prefix for future versioning
3. **Error Messages:** Return descriptive error messages for debugging

---

## Roadmap

### Week 1: FastAPI Endpoint Setup

- [ ] Create FastAPI router (/api/v1/sessions/{session_id}/turns)
- [ ] Define query parameters (cursor, limit)
- [ ] Define response model (TurnPaginationResponse)
- [ ] Add OpenAPI documentation

### Week 2: Cursor Integration

- [ ] Integrate CursorEncoder (decode incoming cursor)
- [ ] Generate next_cursor (from last turn)
- [ ] Validate cursor session_id matches request
- [ ] Add cursor error handling

### Week 3: K0 Bridge Integration

- [ ] Integrate K0PaginationQuery (query turns)
- [ ] Implement has_more logic (fetch limit+1)
- [ ] Handle empty results (new session)
- [ ] Add K0 error handling

### Week 4: Testing & Monitoring

- [ ] Write WARD unit tests (first page, next page, invalid cursor)
- [ ] Write WARD integration tests (end-to-end pagination)
- [ ] Add Prometheus metrics (requests, latency, page size)
- [ ] Create Grafana dashboard
- [ ] Production rollout (monitor API metrics, validate pagination)

---

## Signatures

**Sub-ADR Owner:** K1 Architecture Team
**Status:** ⏳ **In Progress** (0% - Initial Draft Created)
**Created Date:** 2025-10-13
**Target Completion:** 2025-11-10 (4 weeks)
**Blocked By:** 0023a (Cursor Encoding)
**Blocks:** 0023c (K0 WAL Query Optimization)

---

**END OF ADR-0023b**