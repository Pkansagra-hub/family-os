# Contract: K1 Duplicate Request Detection

**Contract ID:** `REST-IDEM-003`
**Status:** DRAFT
**Layer:** K1 API Gateway (REST Response Translation)
**ADR:** ADR-0041b (Idempotency), K0 README Section 9

---

## Purpose

Defines how K1 API Gateway handles duplicate requests by translating K0's 409 responses to REST-friendly 200 OK responses with cached data.

**Architecture:** K0 detects duplicates via SQLite idempotency ledger. K1 receives 409 IDEMPOTENT_DUPLICATE from K0 and translates to 200 OK with `X-Idempotent-Replayed: true` header. Client sees success, not conflict.

---

## Stripe Pattern (Industry Standard)

**Client Behavior:**

```http
POST /v1/sessions HTTP/1.1
Idempotency-Key: req-a1b2c3d4-e5f6-7890-abcd-ef1234567890
Content-Type: application/json

{
  "persona": "helpful-assistant",
  "privacy_band": "GREEN"
}
```

**Expected Response (Duplicate):**
- **Status:** 200 OK (not 409 Conflict)
- **Header:** `X-Idempotent-Replayed: true` (indicates cached response)
- **Body:** Original response from first submission

**Rationale:** Client perspective = "request succeeded" (idempotent operation). 409 Conflict implies client error, but duplicate submission is intentional and safe.

---

## K1 Response Translation

### Case 1: New Request (K0 Returns 200)

**K0 Response:**

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "receipt_id": "rcpt-001",
  "status": "COMMITTED",
  "timestamp": "2025-10-21T14:32:10Z"
}
```

**K1 Translation:**

```python
def translate_k0_response(k0_response, session_data):
    if k0_response.status_code == 200:
        # New request (not a duplicate)
        return Response(
            status_code=201,  # HTTP 201 Created
            headers={
                "Location": f"/v1/sessions/{session_data['session_id']}",
                "X-Receipt-ID": k0_response.json()["receipt_id"],
                "X-Idempotent-Replayed": "false"
            },
            body=session_data
        )
```

---

### Case 2: Duplicate Request (K0 Returns 409)

**K0 Response:**

```http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json

{
  "type": "https://familyos.dev/errors/idempotent-duplicate",
  "title": "Idempotent Duplicate",
  "status": 409,
  "detail": "Request with idem_key already processed",
  "receipt_id": "rcpt-001",
  "first_seen_ts": "2025-10-21T14:32:10Z",
  "cached_response": {
    "session_id": "session-001",
    "status": "ACTIVE",
    "persona": "helpful-assistant"
  }
}
```

**K1 Translation:**

```python
def translate_k0_response(k0_response, session_data=None):
    if k0_response.status_code == 409:
        # Duplicate request (K0 detected via SQLite ledger)
        cached_data = k0_response.json()["cached_response"]
        return Response(
            status_code=200,  # HTTP 200 OK (NOT 409)
            headers={
                "X-Idempotent-Replayed": "true",
                "X-Receipt-ID": k0_response.json()["receipt_id"],
                "X-Original-Timestamp": k0_response.json()["first_seen_ts"]
            },
            body=cached_data  # Return K0's cached response
        )
```

**Client Experience:**
- First submission: 201 Created
- Duplicate submission: 200 OK (appears as success)
- Header distinguishes: `X-Idempotent-Replayed: false` vs `true`

---

## Full Handler Example

```python
@app.post("/v1/sessions")
async def create_session_handler(request: Request):
    # 1. Extract idempotency key (optional)
    idem_key = request.headers.get("Idempotency-Key")

    # 2. Build K0 command envelope
    envelope = {
        "tenant_id": jwt_claims.tenant_id,
        "space_id": jwt_claims.space_id,
        "actor": jwt_claims.sub,
        "topic": "session.create",
        "payload": request.json(),
        "idem_key": idem_key,  # Forwarded to K0
        "trace_id": request.headers.get("X-Trace-ID"),
        "timestamp": datetime.utcnow().isoformat()
    }

    # 3. Call K0 Command Port
    k0_response = await k0_client.submit_command(envelope)

    # 4. Translate K0 response to REST semantics
    if k0_response.status_code == 200:
        # New request
        return Response(
            status_code=201,
            headers={
                "Location": f"/v1/sessions/{session_id}",
                "X-Idempotent-Replayed": "false"
            },
            body=session_data
        )
    elif k0_response.status_code == 409:
        # Duplicate request
        cached_data = k0_response.json()["cached_response"]
        return Response(
            status_code=200,  # Translate 409 → 200
            headers={
                "X-Idempotent-Replayed": "true",
                "X-Receipt-ID": k0_response.json()["receipt_id"]
            },
            body=cached_data
        )
    else:
        # Other K0 errors
        raise K0IntegrationError(k0_response)
```

---

## Performance

### Latency

| Component | New Request | Duplicate Request |
|-----------|-------------|-------------------|
| K1 Processing | <5ms | <5ms |
| K0 Lookup | <25ms P50 | <25ms P50 (SQLite indexed) |
| K0 Response | 200 OK | 409 Conflict |
| K1 Translation | <1ms | <1ms |
| **Total** | **<31ms** | **<31ms** |

**No performance difference:** Duplicate detection is same cost as new request (SQLite indexed lookup).

---

### Duplicate Rate

- **Idempotency key usage:** 8% of POST requests (GitHub data)
- **Duplicate rate:** 8% of requests with keys (network retries, client bugs)
- **Absolute duplicate rate:** 0.64% of all POST requests (8% × 8%)

---

## Observability

### Prometheus Metrics

```python
duplicate_requests_total = Counter(
    'duplicate_requests_total',
    'Total duplicate requests detected (K0 409 responses)',
    ['endpoint']
)

idempotent_replayed_responses_total = Counter(
    'idempotent_replayed_responses_total',
    'Total 200 OK responses with X-Idempotent-Replayed: true',
    ['endpoint']
)

k1_translation_latency_ms = Histogram(
    'k1_translation_latency_ms',
    'K1 response translation latency (409 → 200)',
    buckets=[0.1, 0.5, 1, 2, 5, 10]
)
```

**Example Query:**

```promql
# Duplicate request rate per endpoint
rate(duplicate_requests_total{endpoint="/v1/sessions"}[5m])
```

---

## Error Handling

### Missing Idempotency Key

```python
# Idempotency-Key is optional for POST requests
# If missing, K0 generates hash from envelope fields (ADR K0 Section 9)
idem_key = request.headers.get("Idempotency-Key")  # May be None
envelope["idem_key"] = idem_key  # K0 handles None gracefully
```

**K0 Behavior:**
- If `idem_key` is None, K0 derives from envelope: `BLAKE3(tenant_id | space_id | actor | topic | schema_uri | schema_version | payload_sha256)`
- Client-provided keys override K0 derivation

---

### K0 Returns Other Errors

```python
if k0_response.status_code not in [200, 409]:
    # K0 error (500, 503, 504)
    raise K0IntegrationError(
        status=k0_response.status_code,
        detail=k0_response.json().get("detail", "K0 error"),
        trace_id=envelope["trace_id"]
    )
```

---

## Testing

### Test Cases

```python
@test("K1 translates K0 409 to 200 OK with X-Idempotent-Replayed")
async def test_duplicate_translation():
    # First request (K0 returns 200)
    response1 = await client.post(
        "/v1/sessions",
        headers={"Idempotency-Key": "req-test-123"},
        json={"persona": "assistant", "privacy_band": "GREEN"}
    )
    assert response1.status_code == 201  # Created
    assert response1.headers["X-Idempotent-Replayed"] == "false"
    session_id = response1.json()["session_id"]

    # Duplicate request (K0 returns 409, K1 translates to 200)
    response2 = await client.post(
        "/v1/sessions",
        headers={"Idempotency-Key": "req-test-123"},
        json={"persona": "assistant", "privacy_band": "GREEN"}
    )
    assert response2.status_code == 200  # OK (not 409)
    assert response2.headers["X-Idempotent-Replayed"] == "true"
    assert response2.json()["session_id"] == session_id

@test("missing idempotency key uses K0 hash derivation")
async def test_no_idempotency_key():
    # No idempotency key provided
    response1 = await client.post(
        "/v1/sessions",
        json={"persona": "assistant", "privacy_band": "GREEN"}
    )
    assert response1.status_code == 201

    # Same request (K0 derives same hash, detects duplicate)
    response2 = await client.post(
        "/v1/sessions",
        json={"persona": "assistant", "privacy_band": "GREEN"}
    )
    assert response2.status_code == 200  # Duplicate detected
    assert response2.headers["X-Idempotent-Replayed"] == "true"
```

---

## References

- **K0 README Section 9:** Idempotency & Receipts (SQLite ledger, BLAKE3 hash, 409 response)
- **k0/idem/ledger.py:** Actual duplicate detection implementation
- **ADR-0041b:** REST API Idempotency (K1 response translation)
- **Stripe Idempotency:** https://stripe.com/docs/api/idempotent_requests

---

## Rationale

**Why 200 OK instead of 409 Conflict?**
- **Client perspective:** Duplicate submission succeeded (idempotent operation)
- **409 Conflict:** Implies client error, but idempotency is intentional
- **Stripe pattern:** Return success status (200/201) for duplicates
- **Header differentiation:** `X-Idempotent-Replayed: true` allows clients to detect cached responses

**Why K0 returns 409 internally?**
- **K0 semantics:** 409 IDEMPOTENT_DUPLICATE is accurate (request already committed to WAL)
- **K1 translation layer:** Converts internal K0 semantics to REST API semantics
- **Separation of concerns:** K0 handles storage (409 = duplicate), K1 handles API (200 = success)
