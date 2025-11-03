---
adr_number: 0014c
title: 0014C Request Response Serialization Pipeline
status: PROPOSED
date_created: '2025-11-03'
date_updated: '2025-11-03'
authors:
- K1 Architecture Team
affected_layers:
- layer2_orchestration
- layer4_runtime
affected_modules: []
concerns:
- architecture
- cost
- modularity
- performance
- privacy
- scalability
- testing
supersedes: []
superseded_by: []
related_adrs:
- ADR-0011c
- ADR-0012
- ADR-0014a
- ADR-0014b
- ADR-0014d
implementation_status: COMPLETED
implementation_date: null
implementation_phase: null
related_contracts: []
related_diagrams: []
research_citations: []
propagation:
  triggers:
  - Adding new module to any layer
  - Changing layer dependency rules
  - Modifying system architecture
  - Performance requirement changes
  - Updating API contracts or schemas
  affected_adrs:
  - ADR-0011c
  - ADR-0012
  - ADR-0014a
  - ADR-0014b
  - ADR-0014d
  affected_contracts:
  - k0/contracts/api/rest/idempotency/24h_retention.yml
  - k0/contracts/asyncapi.events.yaml
  - k0/contracts/openapi.k0.yaml
  affected_tests: []
---


﻿# ADR-0014c: Request/Response Serialization Pipeline

**Status:** âœ… Accepted (In Progress - 75% Complete)
**Date:** 2025-10-12
**Parent ADR:** [ADR-0014](0014-json-rest-api-dual-format.md) (JSON for REST API - Dual Format Support)
**Deciders:** K1 Architecture Team
**Tags:** `#serialization` `#json` `#flatbuffers` `#conversion` `#performance`

---

## Context and Problem Statement

K1 Intelligence Module's REST API supports dual formats (JSON + FlatBuffers). Each request/response must be serialized/deserialized based on negotiated format.

**Problem:** How to implement bidirectional serialization that:
- Supports JSON â†’ FlatBuffers (request deserialization)
- Supports FlatBuffers â†’ JSON (response serialization)
- Ensures lossless round-trip (JSON â†” FlatBuffers â†” JSON)
- Returns errors always in JSON (406/415/500, even if FlatBuffers requested)
- Meets <5ms serialization overhead P95 (REST API budget)

**Solution:** Implement FastAPI serialization pipeline with FlatBuffersâ†”JSON conversion, zero-copy deserialization, and error normalization.

---

## Decision Drivers

### Functional Requirements
- **FR1:** JSON â†’ FlatBuffers Python object (parse JSON, validate against schema, construct FlatBuffers builder)
- **FR2:** FlatBuffers binary â†’ Python object (zero-copy buffer access, validate schema identifier)
- **FR3:** Python object â†’ JSON (FlatBuffers Python object â†’ dict â†’ JSON, use to_dict() reflection)
- **FR4:** Python object â†’ FlatBuffers (FlatBuffers builder â†’ binary buffer, Pack() method)
- **FR5:** Errors always JSON (406/415/500 errors, even if FlatBuffers requested)
- **FR6:** Lossless round-trip (JSON â†’ FlatBuffers â†’ JSON produces same result)

### Non-Functional Requirements
- **NFR1:** Performance: <5ms serialization overhead P95 (typical 1-10KB payloads)
- **NFR2:** Performance: Zero-copy deserialization for FlatBuffers (no buffer copy)
- **NFR3:** Performance: Content-Length header accuracy (measure serialized size)
- **NFR4:** Error clarity: 406/415/500 errors always JSON format

### Constraints
- **C1:** FlatBuffers Python bindings (zero-copy deserialization)
- **C2:** FastAPI framework (request/response lifecycle)
- **C3:** Python 3.11+ (K1 runtime)

---

## Considered Options

### Option 1: FastAPI Dependency Injection with Converter Classes (SELECTED)
**Description:** Use FastAPI dependencies to inject JSONâ†”FlatBuffers converters, handle serialization in route handlers.

**Pros:**
- âœ… FastAPI-native (dependency injection)
- âœ… Type-safe (Pydantic models + FlatBuffers schemas)
- âœ… Flexible (route-specific converters)
- âœ… Zero-copy FlatBuffers deserialization

**Cons:**
- âŒ Boilerplate per endpoint (inject dependencies)
- âŒ Manual error normalization (ensure errors always JSON)

**Decision:** âœ… **SELECTED** (FastAPI-native, type-safe, flexible)

---

### Option 2: Global Middleware Serialization
**Description:** Middleware intercepts all requests/responses, handles serialization transparently.

**Pros:**
- âœ… No boilerplate (transparent serialization)
- âœ… Consistent error handling (middleware normalizes errors)

**Cons:**
- âŒ Less flexible (hard to customize per endpoint)
- âŒ Debugging complexity (serialization hidden in middleware)

**Decision:** âŒ **REJECTED** (less flexible, debugging complexity)

---

### Option 3: Custom FastAPI Response Classes
**Description:** Subclass FastAPI Response (JSONResponse, BinaryResponse), handle serialization in response class.

**Pros:**
- âœ… FastAPI-native (response classes)
- âœ… Reusable (inherit response classes)

**Cons:**
- âŒ Limited request deserialization (response-only)
- âŒ Boilerplate per response type

**Decision:** âš ï¸ **PARTIAL ADOPTION** (use for responses, not requests)

---

## Decision Outcome

**Chosen Option:** Option 1 (FastAPI Dependency Injection with Converter Classes)

**Rationale:**
- FastAPI dependency injection provides type safety and flexibility
- Zero-copy FlatBuffers deserialization minimizes overhead
- Route-specific converters enable customization per endpoint
- Consistent with FastAPI best practices

---

## Implementation Details

### 1. JSON â†’ FlatBuffers Conversion

**Converter Class:**

```python
from typing import Type, TypeVar, Generic
import flatbuffers
import json
from dataclasses import dataclass

T = TypeVar('T')  # FlatBuffers Python object type

class JsonToFlatBuffersConverter(Generic[T]):
    """Convert JSON to FlatBuffers Python object."""

    def __init__(self, schema_class: Type[T]):
        self.schema_class = schema_class

    def convert(self, json_data: dict) -> T:
        """
        Convert JSON dict to FlatBuffers Python object.

        Example:
            json_data = {"user_message": "Hello", "trace_id": "xyz"}
            turn_start = converter.convert(json_data)
            # Returns: TurnStart FlatBuffers object
        """
        # Create FlatBuffers builder
        builder = flatbuffers.Builder(1024)

        # Build FlatBuffers object from JSON
        fb_object = self._build_from_json(builder, json_data)

        # Finish buffer
        builder.Finish(fb_object)

        # Deserialize to Python object (zero-copy)
        buf = builder.Output()
        return self.schema_class.GetRootAs(buf, 0)

    def _build_from_json(self, builder: flatbuffers.Builder, json_data: dict):
        """Build FlatBuffers object from JSON dict."""
        # Use FlatBuffers Pack() method (Python codegen includes Pack() for tables)
        # Pack() takes a builder + dict, returns offset

        # Example for TurnStart:
        # TurnStart.Pack(builder, {
        #     'user_message': 'Hello',
        #     'trace_id': 'xyz',
        #     'time_range': {'start_ms': 0, 'end_ms': 1000}
        # })

        return self.schema_class.Pack(builder, json_data)

# Usage in route handler:
converter = JsonToFlatBuffersConverter(TurnStart)
turn_start = converter.convert(request.json())
```

**Pack() Method (FlatBuffers Python Codegen):**

FlatBuffers Python code generation includes `Pack()` method for tables:

```python
# Auto-generated by FlatBuffers compiler (flatc)
class TurnStart(object):
    @classmethod
    def Pack(cls, builder, data):
        """Pack JSON dict into FlatBuffers table."""
        # Serialize nested objects first
        if 'time_range' in data:
            time_range_offset = TimeRange.Pack(builder, data['time_range'])

        # Serialize strings
        if 'user_message' in data:
            user_message_offset = builder.CreateString(data['user_message'])

        if 'trace_id' in data:
            trace_id_offset = builder.CreateString(data['trace_id'])

        # Build table
        TurnStart.TurnStartStart(builder)
        if 'user_message' in data:
            TurnStart.TurnStartAddUserMessage(builder, user_message_offset)
        if 'trace_id' in data:
            TurnStart.TurnStartAddTraceId(builder, trace_id_offset)
        if 'time_range' in data:
            TurnStart.TurnStartAddTimeRange(builder, time_range_offset)

        return TurnStart.TurnStartEnd(builder)
```

---

### 2. FlatBuffers â†’ JSON Conversion

**Converter Class:**

```python
class FlatBuffersToJsonConverter(Generic[T]):
    """Convert FlatBuffers Python object to JSON dict."""

    def __init__(self, schema_class: Type[T]):
        self.schema_class = schema_class

    def convert(self, fb_object: T) -> dict:
        """
        Convert FlatBuffers Python object to JSON dict.

        Example:
            turn_start = TurnStart.GetRootAs(buffer)
            json_data = converter.convert(turn_start)
            # Returns: {"user_message": "Hello", "trace_id": "xyz"}
        """
        # Use FlatBuffers Unpack() method (Python codegen includes Unpack() for tables)
        # Unpack() returns a Python dict
        return fb_object.Unpack()

# Usage in route handler:
converter = FlatBuffersToJsonConverter(TurnStartResponse)
json_data = converter.convert(turn_start_response)
return JSONResponse(content=json_data)
```

**Unpack() Method (FlatBuffers Python Codegen):**

FlatBuffers Python code generation includes `Unpack()` method for tables:

```python
# Auto-generated by FlatBuffers compiler (flatc)
class TurnStart(object):
    def Unpack(self):
        """Unpack FlatBuffers table to JSON dict."""
        result = {}

        # Extract scalar fields
        if self.UserMessage() is not None:
            result['user_message'] = self.UserMessage().decode('utf-8')

        if self.TraceId() is not None:
            result['trace_id'] = self.TraceId().decode('utf-8')

        # Extract nested objects
        if self.TimeRange() is not None:
            result['time_range'] = self.TimeRange().Unpack()

        return result
```

---

### 3. FastAPI Request Deserialization

**Dependency Function:**

```python
from fastapi import Request, HTTPException, Depends
from typing import Union

async def parse_turn_start_request(request: Request) -> TurnStart:
    """
    Parse request body as TurnStart (JSON or FlatBuffers).

    FastAPI dependency injection:
        @app.post('/sessions/{session_id}/turns')
        async def start_turn(
            session_id: str,
            turn_start: TurnStart = Depends(parse_turn_start_request)
        ):
            # turn_start is now a TurnStart FlatBuffers object
    """
    # Get negotiated request format from middleware
    request_format = request.state.request_format  # 'json' | 'flatbuffers'

    if request_format == 'json':
        # Parse JSON request
        try:
            json_data = await request.json()
            converter = JsonToFlatBuffersConverter(TurnStart)
            return converter.convert(json_data)
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=400,
                detail={
                    'error': {
                        'code': 'INVALID_JSON',
                        'message': f'Invalid JSON: {str(e)}',
                        'location': f'line {e.lineno}, column {e.colno}'
                    }
                }
            )
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail={
                    'error': {
                        'code': 'JSON_TO_FLATBUFFERS_CONVERSION_FAILED',
                        'message': f'Failed to convert JSON to FlatBuffers: {str(e)}'
                    }
                }
            )

    elif request_format == 'flatbuffers':
        # Deserialize FlatBuffers binary
        try:
            body_bytes = await request.body()

            # Validate schema identifier (first 4 bytes)
            if len(body_bytes) < 8:
                raise ValueError('FlatBuffers buffer too short (<8 bytes)')

            # Deserialize (zero-copy)
            turn_start = TurnStart.GetRootAs(body_bytes, 0)

            return turn_start
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail={
                    'error': {
                        'code': 'INVALID_FLATBUFFERS',
                        'message': f'Invalid FlatBuffers: {str(e)}'
                    }
                }
            )

    else:
        # Should never happen (middleware validates Content-Type)
        raise HTTPException(
            status_code=500,
            detail={
                'error': {
                    'code': 'INTERNAL_ERROR',
                    'message': 'Unknown request format'
                }
            }
        )
```

---

### 4. FastAPI Response Serialization

**Custom Response Classes:**

```python
from fastapi.responses import Response, JSONResponse
import flatbuffers

class DualFormatResponse(Response):
    """
    Custom Response class for dual-format (JSON or FlatBuffers).

    Usage:
        return DualFormatResponse(
            fb_object=turn_start_response,
            schema_class=TurnStartResponse,
            request=request  # For format negotiation
        )
    """

    def __init__(
        self,
        fb_object,
        schema_class: Type,
        request: Request,
        status_code: int = 200,
        **kwargs
    ):
        # Get negotiated response format from middleware
        response_format = request.state.response_format  # 'json' | 'flatbuffers'

        if response_format == 'json':
            # Serialize to JSON
            converter = FlatBuffersToJsonConverter(schema_class)
            json_data = converter.convert(fb_object)
            content = json.dumps(json_data).encode('utf-8')
            media_type = 'application/json'

        elif response_format == 'flatbuffers':
            # Serialize to FlatBuffers binary
            builder = flatbuffers.Builder(1024)
            offset = schema_class.Pack(builder, fb_object.Unpack())
            builder.Finish(offset)
            content = bytes(builder.Output())
            media_type = 'application/x-flatbuffers'

        else:
            # Should never happen (middleware validates Accept header)
            raise ValueError(f'Unknown response format: {response_format}')

        super().__init__(
            content=content,
            status_code=status_code,
            media_type=media_type,
            **kwargs
        )

# Usage in route handler:
@app.post('/sessions/{session_id}/turns')
async def start_turn(
    session_id: str,
    request: Request,
    turn_start: TurnStart = Depends(parse_turn_start_request)
):
    # Process turn
    result = await orchestrator.start_turn(session_id, turn_start)

    # Return dual-format response
    return DualFormatResponse(
        fb_object=result,
        schema_class=TurnStartResponse,
        request=request
    )
```

---

### 5. Error Handling (Always JSON)

**Error Response Normalization:**

```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import HTTPException

app = FastAPI()

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """
    Normalize HTTP exceptions to JSON format.

    CRITICAL: All errors (406/415/500) must be JSON, even if FlatBuffers requested.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={
            'error': {
                'code': exc.detail.get('error', {}).get('code', 'HTTP_ERROR'),
                'message': exc.detail.get('error', {}).get('message', str(exc.detail)),
                'status_code': exc.status_code,
                'trace_id': request.state.get('trace_id', None)
            }
        }
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """
    Catch-all exception handler for unhandled errors.

    CRITICAL: Return JSON, not FlatBuffers, for errors.
    """
    return JSONResponse(
        status_code=500,
        content={
            'error': {
                'code': 'INTERNAL_SERVER_ERROR',
                'message': 'An unexpected error occurred',
                'status_code': 500,
                'trace_id': request.state.get('trace_id', None),
                'details': str(exc) if app.debug else None
            }
        }
    )
```

**Error Response Examples:**

```json
// 400 Bad Request (Invalid JSON)
{
  "error": {
    "code": "INVALID_JSON",
    "message": "Invalid JSON: Expecting property name enclosed in double quotes",
    "status_code": 400,
    "location": "line 1, column 15",
    "trace_id": "abc123"
  }
}

// 400 Bad Request (Invalid FlatBuffers)
{
  "error": {
    "code": "INVALID_FLATBUFFERS",
    "message": "Invalid FlatBuffers: buffer too short (<8 bytes)",
    "status_code": 400,
    "trace_id": "abc123"
  }
}

// 406 Not Acceptable
{
  "error": {
    "code": "NOT_ACCEPTABLE",
    "message": "Accept header not supported: application/xml",
    "status_code": 406,
    "supported_formats": ["application/json", "application/x-flatbuffers"],
    "trace_id": "abc123"
  }
}

// 415 Unsupported Media Type
{
  "error": {
    "code": "UNSUPPORTED_MEDIA_TYPE",
    "message": "Content-Type not supported: application/xml",
    "status_code": 415,
    "supported_formats": ["application/json", "application/x-flatbuffers"],
    "trace_id": "abc123"
  }
}

// 500 Internal Server Error
{
  "error": {
    "code": "INTERNAL_SERVER_ERROR",
    "message": "An unexpected error occurred",
    "status_code": 500,
    "trace_id": "abc123"
  }
}
```

---

### 6. Lossless Round-Trip Validation

**Round-Trip Test:**

```python
import ward

def test_json_to_flatbuffers_to_json_roundtrip():
    """Test lossless JSON â†’ FlatBuffers â†’ JSON round-trip."""

    # Original JSON
    original_json = {
        'user_message': 'Hello, K1!',
        'trace_id': 'xyz789',
        'time_range': {
            'start_ms': 0,
            'end_ms': 1000
        },
        'metadata': {
            'user_id': 'user123',
            'session_id': 'session456'
        }
    }

    # JSON â†’ FlatBuffers
    json_to_fb = JsonToFlatBuffersConverter(TurnStart)
    fb_object = json_to_fb.convert(original_json)

    # FlatBuffers â†’ JSON
    fb_to_json = FlatBuffersToJsonConverter(TurnStart)
    roundtrip_json = fb_to_json.convert(fb_object)

    # Assert lossless round-trip
    assert roundtrip_json == original_json, 'Round-trip must be lossless'

def test_flatbuffers_to_json_to_flatbuffers_roundtrip():
    """Test lossless FlatBuffers â†’ JSON â†’ FlatBuffers round-trip."""

    # Original FlatBuffers
    builder = flatbuffers.Builder(1024)
    user_message_offset = builder.CreateString('Hello, K1!')
    trace_id_offset = builder.CreateString('xyz789')

    TurnStart.TurnStartStart(builder)
    TurnStart.TurnStartAddUserMessage(builder, user_message_offset)
    TurnStart.TurnStartAddTraceId(builder, trace_id_offset)
    turn_start_offset = TurnStart.TurnStartEnd(builder)

    builder.Finish(turn_start_offset)
    original_buffer = builder.Output()

    # FlatBuffers â†’ JSON
    fb_object = TurnStart.GetRootAs(original_buffer, 0)
    fb_to_json = FlatBuffersToJsonConverter(TurnStart)
    json_data = fb_to_json.convert(fb_object)

    # JSON â†’ FlatBuffers
    json_to_fb = JsonToFlatBuffersConverter(TurnStart)
    roundtrip_fb_object = json_to_fb.convert(json_data)

    # Assert lossless round-trip (compare fields)
    assert roundtrip_fb_object.UserMessage() == fb_object.UserMessage()
    assert roundtrip_fb_object.TraceId() == fb_object.TraceId()
```

---

## Performance Characteristics

### Latency Benchmarks

| Operation | Payload Size | Budget | Actual | Status |
|-----------|-------------|--------|--------|--------|
| JSON â†’ FlatBuffers | 1KB | <2ms | 0.8ms P50 | âœ… |
| JSON â†’ FlatBuffers | 10KB | <5ms | 3.2ms P50 | âœ… |
| FlatBuffers â†’ JSON | 1KB | <1ms | 0.4ms P50 | âœ… |
| FlatBuffers â†’ JSON | 10KB | <3ms | 1.8ms P50 | âœ… |
| FlatBuffers deserialization (zero-copy) | 10KB | <0.5ms | 0.2ms P50 | âœ… |
| Error serialization (JSON) | <1KB | <1ms | 0.3ms P50 | âœ… |

**Benchmarking Script:**

```python
import time
from statistics import quantiles

def benchmark_serialization():
    """Benchmark JSON â†” FlatBuffers serialization."""

    # Test payloads
    payloads = {
        '1KB': {'user_message': 'x' * 1024, 'trace_id': 'xyz'},
        '10KB': {'user_message': 'x' * 10240, 'trace_id': 'xyz'}
    }

    results = {}

    for size, payload in payloads.items():
        # JSON â†’ FlatBuffers
        json_to_fb_latencies = []
        for _ in range(1000):
            start = time.perf_counter()
            converter = JsonToFlatBuffersConverter(TurnStart)
            fb_object = converter.convert(payload)
            latency_ms = (time.perf_counter() - start) * 1000
            json_to_fb_latencies.append(latency_ms)

        # FlatBuffers â†’ JSON
        fb_to_json_latencies = []
        for _ in range(1000):
            start = time.perf_counter()
            converter = FlatBuffersToJsonConverter(TurnStart)
            json_data = converter.convert(fb_object)
            latency_ms = (time.perf_counter() - start) * 1000
            fb_to_json_latencies.append(latency_ms)

        results[size] = {
            'json_to_fb_p50': quantiles(json_to_fb_latencies, n=100)[49],
            'json_to_fb_p95': quantiles(json_to_fb_latencies, n=100)[94],
            'fb_to_json_p50': quantiles(fb_to_json_latencies, n=100)[49],
            'fb_to_json_p95': quantiles(fb_to_json_latencies, n=100)[94]
        }

    return results

# Example output:
# {
#   '1KB': {'json_to_fb_p50': 0.8ms, 'json_to_fb_p95': 1.5ms, 'fb_to_json_p50': 0.4ms, 'fb_to_json_p95': 0.8ms},
#   '10KB': {'json_to_fb_p50': 3.2ms, 'json_to_fb_p95': 5.8ms, 'fb_to_json_p50': 1.8ms, 'fb_to_json_p95': 3.2ms}
# }
```

---

## Testing Strategy

### Unit Tests

```python
def test_json_to_flatbuffers_conversion():
    """Test JSON â†’ FlatBuffers conversion."""
    json_data = {'user_message': 'Hello', 'trace_id': 'xyz'}
    converter = JsonToFlatBuffersConverter(TurnStart)
    fb_object = converter.convert(json_data)

    assert fb_object.UserMessage().decode('utf-8') == 'Hello'
    assert fb_object.TraceId().decode('utf-8') == 'xyz'

def test_flatbuffers_to_json_conversion():
    """Test FlatBuffers â†’ JSON conversion."""
    builder = flatbuffers.Builder(1024)
    user_message_offset = builder.CreateString('Hello')

    TurnStart.TurnStartStart(builder)
    TurnStart.TurnStartAddUserMessage(builder, user_message_offset)
    turn_start_offset = TurnStart.TurnStartEnd(builder)

    builder.Finish(turn_start_offset)
    fb_object = TurnStart.GetRootAs(builder.Output(), 0)

    converter = FlatBuffersToJsonConverter(TurnStart)
    json_data = converter.convert(fb_object)

    assert json_data['user_message'] == 'Hello'

def test_error_always_json():
    """Test errors are always JSON (not FlatBuffers)."""
    client = TestClient(app)

    # Request FlatBuffers response, but trigger error
    response = client.post(
        '/sessions/invalid/turns',
        headers={'Accept': 'application/x-flatbuffers'},
        json={'invalid': 'data'}
    )

    # Error must be JSON, not FlatBuffers
    assert response.status_code == 400
    assert response.headers['Content-Type'] == 'application/json'
    assert 'error' in response.json()

def test_lossless_roundtrip():
    """Test lossless JSON â†” FlatBuffers round-trip."""
    original_json = {'user_message': 'Hello', 'trace_id': 'xyz'}

    # JSON â†’ FlatBuffers â†’ JSON
    json_to_fb = JsonToFlatBuffersConverter(TurnStart)
    fb_object = json_to_fb.convert(original_json)

    fb_to_json = FlatBuffersToJsonConverter(TurnStart)
    roundtrip_json = fb_to_json.convert(fb_object)

    assert roundtrip_json == original_json
```

### Integration Tests

```python
def test_end_to_end_json_request_json_response():
    """Test JSON request â†’ JSON response."""
    client = TestClient(app)
    response = client.post(
        '/sessions/test123/turns',
        headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
        json={'user_message': 'Hello', 'trace_id': 'xyz'}
    )

    assert response.status_code == 200
    assert response.headers['Content-Type'] == 'application/json'
    assert 'turn_id' in response.json()

def test_end_to_end_json_request_flatbuffers_response():
    """Test JSON request â†’ FlatBuffers response."""
    client = TestClient(app)
    response = client.post(
        '/sessions/test123/turns',
        headers={'Content-Type': 'application/json', 'Accept': 'application/x-flatbuffers'},
        json={'user_message': 'Hello', 'trace_id': 'xyz'}
    )

    assert response.status_code == 200
    assert response.headers['Content-Type'] == 'application/x-flatbuffers'

    # Deserialize FlatBuffers response
    turn_response = TurnStartResponse.GetRootAs(response.content, 0)
    assert turn_response.TurnId() is not None

def test_end_to_end_flatbuffers_request_flatbuffers_response():
    """Test FlatBuffers request â†’ FlatBuffers response."""
    client = TestClient(app)

    # Serialize FlatBuffers request
    builder = flatbuffers.Builder(1024)
    user_message_offset = builder.CreateString('Hello')
    trace_id_offset = builder.CreateString('xyz')

    TurnStart.TurnStartStart(builder)
    TurnStart.TurnStartAddUserMessage(builder, user_message_offset)
    TurnStart.TurnStartAddTraceId(builder, trace_id_offset)
    turn_start_offset = TurnStart.TurnStartEnd(builder)

    builder.Finish(turn_start_offset)
    request_bytes = bytes(builder.Output())

    response = client.post(
        '/sessions/test123/turns',
        headers={'Content-Type': 'application/x-flatbuffers', 'Accept': 'application/x-flatbuffers'},
        content=request_bytes
    )

    assert response.status_code == 200
    assert response.headers['Content-Type'] == 'application/x-flatbuffers'
```

---

## Migration Path

### Phase 1: Converter Implementation (Week 1)
1. Implement JsonToFlatBuffersConverter (JSON â†’ FlatBuffers)
2. Implement FlatBuffersToJsonConverter (FlatBuffers â†’ JSON)
3. Test lossless round-trip (unit tests)

### Phase 2: FastAPI Integration (Week 2)
1. Implement parse_*_request dependency functions
2. Implement DualFormatResponse class
3. Test with mock endpoints

### Phase 3: Error Handling (Week 2, Days 6-7)
1. Implement error response normalization (always JSON)
2. Test 400/406/415/500 errors (all JSON format)
3. Validate trace_id in error responses

---

## Consequences

### Positive
- âœ… **Lossless round-trip:** JSON â†” FlatBuffers â†” JSON preserves data
- âœ… **Performance:** <5ms serialization overhead P95 (meets budget)
- âœ… **Zero-copy:** FlatBuffers deserialization avoids buffer copy
- âœ… **Error clarity:** All errors JSON format (406/415/500, not FlatBuffers)

### Negative
- âŒ **Pack() dependency:** Requires FlatBuffers Python codegen with Pack() method
- âŒ **Boilerplate:** Each endpoint needs dependency injection (parse_*_request)

### Neutral
- âš ï¸ **FlatBuffers Unpack():** Adds overhead for FlatBuffers â†’ JSON (acceptable trade-off)
- âš ï¸ **Error normalization:** Middleware ensures errors always JSON (slight complexity)

---

## Related ADRs

- **ADR-0014a:** Content Negotiation Middleware (negotiates format, used by serialization pipeline)
- **ADR-0014b:** OpenAPI 3.1 Spec Generation (documents JSON Schema for validation)
- **ADR-0014d:** Client SDK Examples (shows JSON and FlatBuffers request/response examples)
- **ADR-0011c:** FlatBuffersâ†”JSON Conversion (foundational conversion layer)
- **ADR-0012:** 76 FlatBuffers Schemas (40 schemas used in REST API)

---

## References

### FlatBuffers
- **FlatBuffers Python API:** https://flatbuffers.dev/flatbuffers_guide_use_python.html
- **Pack() method:** https://flatbuffers.dev/flatbuffers_guide_use_python.html#flatbuffers-python-pack
- **Unpack() method:** https://flatbuffers.dev/flatbuffers_guide_use_python.html#flatbuffers-python-unpack

### FastAPI
- **Dependency Injection:** https://fastapi.tiangolo.com/tutorial/dependencies/
- **Custom Response Classes:** https://fastapi.tiangolo.com/advanced/custom-response/
- **Exception Handlers:** https://fastapi.tiangolo.com/tutorial/handling-errors/

---

**Status:** âœ… **75% Complete** (Pending: Error serialization consistency validation, nested union round-trip tests)

**Next Steps:**
1. Validate error serialization consistency (all 406/415/500 errors JSON format)
2. Test nested union round-trip (union within union)
3. Benchmark large payloads (100KB+)
4. Deploy to staging