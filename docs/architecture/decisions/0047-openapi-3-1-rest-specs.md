# ADR-0047: OpenAPI 3.1 Specification for REST API Documentation

**Status:** ✅ Approved
**Date:** 2025-10-12
**Authors:** K1 Architecture Team
**Category:** API Documentation & Developer Experience
**Related ADRs:** ADR-0041 (REST API Session Management), ADR-0014 (JSON for REST API), ADR-0011 (FlatBuffers Serialization)

> **⚠️ ARCHITECTURAL NOTE:** This ADR governs auto-generated OpenAPI 3.1 specification for K1 REST API, providing interactive documentation (Swagger UI, ReDoc), schema validation, client SDK generation, and FlatBuffers schema annotations. OpenAPI spec is generated from code annotations (FastAPI/Pydantic models), ensuring documentation stays synchronized with implementation. Available at `/v1/openapi.json` (JSON) and `/v1/openapi.yaml` (YAML) with interactive explorers at `/docs` (Swagger UI) and `/redoc` (ReDoc).

---

## Context

### Hybrid Architecture Context

**OpenAPI 3.1 specification provides auto-generated REST API documentation from code annotations (FastAPI decorators + Pydantic models), enabling interactive testing (Swagger UI at `/docs`, ReDoc at `/redoc`), schema validation (request/response schemas enforce contracts), client SDK generation (TypeScript, Python, Go clients auto-generated from spec), FlatBuffers schema annotations (document binary serialization option alongside JSON), versioning support (URL-based `/v1/`, `/v2/` with deprecation notices), and developer self-service (no manual wiki updates, always synchronized with code).**

#### Critical Insight: Why Auto-Generated OpenAPI 3.1 (Not Manual Documentation)

Without auto-generated OpenAPI, **documentation written manually** (Markdown in wiki, separate from code), **out-of-sync risk** (90% of manual docs become stale within 6 months = developer frustration), **no schema validation** (JSON examples in wiki don't enforce actual API contracts), **no interactive testing** (developers must use curl/Postman, copy-paste examples from wiki), and **no SDK generation** (manual client code for TypeScript/Python/Go = 3× development time). Auto-generated OpenAPI 3.1 achieves **always synchronized** (generated from code annotations, impossible to drift), **schema validation** (Pydantic models enforce request/response contracts at runtime), **interactive testing** (Swagger UI live sandbox, no curl/Postman needed), **SDK generation** (OpenAPI Generator creates TypeScript/Python/Go clients in 5 minutes vs 3 days manual coding), and **versioning support** (URL-based `/v1/`, `/v2/` with deprecation metadata in spec).

#### Decision Matrix: 5 Alternatives for API Documentation

| Alternative | Sync Guarantee | Interactive Testing | Schema Validation | SDK Generation | Maintenance | Score | Decision |
|-------------|---------------|-------------------|------------------|---------------|-------------|-------|----------|
| **Manual Markdown Wiki** | ❌ No (stale) | ❌ No | ❌ No | ❌ Manual | High (manual updates) | **2/10** | ❌ REJECTED |
| **Postman Collections** | ❌ No (separate) | ✅ Yes | Partial | Partial | Medium | **5/10** | ❌ REJECTED |
| **GraphQL Schema** | ✅ Yes (introspection) | ✅ Yes | ✅ Yes | ✅ Yes | Low | **8/10** | ❌ REJECTED |
| **OpenAPI 3.1 Auto-Generated** | ✅ Yes (from code) | ✅ Swagger UI | ✅ Pydantic | ✅ OpenAPI Generator | Low | **10/10** | ✅ SELECTED |
| **gRPC Proto + grpc-gateway** | ✅ Yes (proto) | Partial | ✅ Yes | ✅ Yes | Medium | **7/10** | ❌ REJECTED |

**Key Decision Factors:**

1. **Always Synchronized:** OpenAPI spec generated from FastAPI code annotations (Pydantic models, decorator parameters) = impossible to drift (vs manual wiki 90% stale in 6 months)
2. **Interactive Testing:** Swagger UI at `/docs` provides live sandbox (try endpoints with JWT, see real responses) vs manual curl/Postman copy-paste
3. **Schema Validation:** Pydantic models enforce request/response contracts at runtime (400 Bad Request if invalid JSON) vs manual wiki examples don't enforce anything
4. **SDK Generation:** OpenAPI Generator creates TypeScript/Python/Go clients in 5 minutes (vs 3 days manual coding), always synchronized with API changes
5. **Low Maintenance:** Zero manual updates (OpenAPI spec auto-generated on every code change) vs manual wiki requires 2-4 hours per feature

---

### Problem Statement

**K1 REST API developers need auto-generated OpenAPI 3.1 specification with interactive documentation (Swagger UI, ReDoc), schema validation (Pydantic models), client SDK generation (TypeScript, Python, Go), FlatBuffers binary option annotations, versioning support (`/v1/`, `/v2/`), and developer self-service (no manual wiki updates), ensuring documentation stays synchronized with code and enabling rapid client integration.**

**Current Challenge:** Without auto-generated OpenAPI:

**Problem 1: Manual Documentation Drift**
- REST API documented in manual Markdown wiki (separate from code)
- Developers update code but forget to update wiki
- **90% of manual docs become stale within 6 months**
- **Risk:** Developer frustration, incorrect API usage, support burden

**Problem 2: No Interactive Testing**
- Developers must use curl or Postman
- Copy-paste JSON examples from wiki (error-prone)
- No live sandbox to try endpoints with JWT
- **Risk:** High onboarding friction, wasted time debugging JSON typos

**Problem 3: No Schema Validation**
- JSON examples in wiki don't enforce contracts
- API implementation changes but wiki examples don't
- Developers send invalid requests, get 400 Bad Request with cryptic errors
- **Risk:** Poor developer experience, high support burden

**Problem 4: Manual Client SDK Development**
- TypeScript, Python, Go clients written manually
- 3 days per language per API version
- Manual updates when API changes
- **Risk:** Slow client integration, SDK drift from API

**Real-World Scenario (Without Auto-Generated OpenAPI):**
```
Developer wants to integrate K1 REST API:

Without OpenAPI:
- Read manual Markdown wiki: docs/api_reference.md
  → Example shows POST /v1/sessions with JSON body
  → Copy-paste JSON example to Postman
  → Example is 6 months old, missing new "timeout_ms" field
- Send request: POST /v1/sessions with old JSON
  → 400 Bad Request: "Missing required field: timeout_ms"
  → Frustration: "Documentation is wrong!"
- Write TypeScript client manually (3 days):
  - Define interfaces for SessionCreate, Turn, etc.
  - Implement fetch() calls with Authorization header
  - Handle errors, retries, pagination
- API changes next month (add "priority" field):
  - Manual wiki not updated (stale)
  - TypeScript client breaks (missing "priority")
  - 1 day to fix client (find changes, update interfaces)

Problems:
- Manual wiki stale (6 months old) ❌
- No interactive testing (copy-paste errors) ❌
- No schema validation (cryptic 400 errors) ❌
- Manual client SDK (3 days + 1 day per change) ❌
- High support burden (frustrated developers) ❌
```

**With Auto-Generated OpenAPI 3.1:**
```
Developer wants to integrate K1 REST API:

With OpenAPI:
- Browse Swagger UI: https://api.k1.example.com/docs
  → Interactive documentation (always synchronized with code)
  → Click "POST /v1/sessions" → "Try it out"
  → Fill form: JWT token, JSON body (schema validated)
  → Click "Execute" → See real response (200 OK)
  → All fields documented (timeout_ms, priority, etc.)
- Generate TypeScript client (5 minutes):
  - Download OpenAPI spec: GET /v1/openapi.json
  - Run: openapi-generator-cli generate -i openapi.json -g typescript-axios -o ./client
  - Import client: import { SessionsApi } from './client'
  - Use client: await sessionsApi.createSession({ timeout_ms: 30000, priority: "REALTIME" })
- API changes next month (add "priority" field):
  - OpenAPI spec auto-updates (generated from code)
  - Re-generate TypeScript client (5 minutes)
  - TypeScript compiler shows type errors (must add "priority")
  - Fix client code (1 hour vs 1 day manual)

Benefits:
- OpenAPI always synchronized (generated from code) ✅
- Interactive testing (Swagger UI sandbox) ✅
- Schema validation (Pydantic models enforce contracts) ✅
- Auto-generated client SDK (5 minutes vs 3 days) ✅
- Low support burden (self-service documentation) ✅
```

---

## Decision

**Implement auto-generated OpenAPI 3.1 specification using FastAPI + Pydantic models, with interactive documentation (Swagger UI at `/docs`, ReDoc at `/redoc`), JSON + YAML formats (`/v1/openapi.json`, `/v1/openapi.yaml`), schema validation, client SDK generation support, FlatBuffers annotations, and versioning.**

### OpenAPI Endpoints

| Endpoint | Format | Purpose | Cache |
|----------|--------|---------|-------|
| `/v1/openapi.json` | JSON | Machine-readable spec for SDK generation | 1 hour |
| `/v1/openapi.yaml` | YAML | Human-readable spec for review | 1 hour |
| `/docs` | HTML | Swagger UI (interactive sandbox) | No cache |
| `/redoc` | HTML | ReDoc (clean documentation) | No cache |

### Core Components

#### 1. FastAPI Auto-Generation (Code Annotations)

**File:** `k1/api/rest/sessions.py`

```python
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, Field
from typing import Optional, List

router = APIRouter(prefix="/v1/sessions", tags=["Sessions"])

class CreateSessionRequest(BaseModel):
    """Request to create a new session"""
    persona_id: Optional[str] = Field(None, description="Persona ID (default: family assistant)")
    timeout_ms: int = Field(30000, description="Session timeout in milliseconds", ge=1000, le=300000)
    priority: str = Field("INTERACTIVE", description="Priority level", pattern="^(URGENT|REALTIME|INTERACTIVE|BACKGROUND)$")

    class Config:
        schema_extra = {
            "example": {
                "persona_id": "persona_family_assistant",
                "timeout_ms": 30000,
                "priority": "INTERACTIVE"
            }
        }

class Session(BaseModel):
    """Session resource"""
    session_id: str = Field(..., description="Unique session identifier")
    user_id: str = Field(..., description="User who owns the session")
    persona_id: str = Field(..., description="Active persona")
    created_at: str = Field(..., description="ISO 8601 timestamp")
    status: str = Field(..., description="Session status: ACTIVE, IDLE, EXPIRED")

    class Config:
        schema_extra = {
            "example": {
                "session_id": "ses_1a2b3c4d5e6f",
                "user_id": "usr_9z8y7x6w5v4u",
                "persona_id": "persona_family_assistant",
                "created_at": "2025-10-12T10:30:00Z",
                "status": "ACTIVE"
            }
        }

@router.post(
    "",
    response_model=Session,
    status_code=201,
    summary="Create a new session",
    description="""
    Create a new K1 session for conversational AI interaction.

    **Authentication:** Bearer JWT token required.

    **Rate Limit:** 100 requests/hour per user.

    **Returns:** Session resource with session_id.

    **Errors:**
    - 400: Invalid request (missing required fields, invalid priority)
    - 401: Unauthorized (missing/invalid JWT)
    - 429: Rate limit exceeded
    - 500: Internal server error
    """,
    responses={
        201: {"description": "Session created successfully", "model": Session},
        400: {"description": "Bad Request", "content": {"application/json": {"example": {"type": "/errors/invalid-request", "title": "Invalid Request", "status": 400, "detail": "Invalid priority: must be URGENT, REALTIME, INTERACTIVE, or BACKGROUND"}}}},
        401: {"description": "Unauthorized"},
        429: {"description": "Rate Limit Exceeded"},
        500: {"description": "Internal Server Error"}
    },
    tags=["Sessions"]
)
async def create_session(
    request: CreateSessionRequest,
    authorization: str = Header(..., description="Bearer JWT token")
) -> Session:
    """
    Create a new session.

    OpenAPI automatically generates:
    - Request schema from CreateSessionRequest Pydantic model
    - Response schema from Session Pydantic model
    - Parameter descriptions from Field() descriptions
    - Example JSON from Config.schema_extra
    - Error responses from responses parameter
    """
    # Implementation
    pass
```

**Generated OpenAPI Schema:**

```json
{
  "openapi": "3.1.0",
  "info": {
    "title": "K1 Intelligence Module REST API",
    "version": "1.0.0",
    "description": "K1 Intelligence Module REST API for session management, turn submission, and conversation retrieval.",
    "contact": {
      "name": "K1 API Support",
      "email": "api-support@k1.example.com"
    }
  },
  "servers": [
    {"url": "https://api.k1.example.com", "description": "Production"},
    {"url": "https://staging-api.k1.example.com", "description": "Staging"}
  ],
  "paths": {
    "/v1/sessions": {
      "post": {
        "summary": "Create a new session",
        "description": "Create a new K1 session for conversational AI interaction...",
        "operationId": "create_session",
        "tags": ["Sessions"],
        "security": [{"bearerAuth": []}],
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {"$ref": "#/components/schemas/CreateSessionRequest"},
              "example": {
                "persona_id": "persona_family_assistant",
                "timeout_ms": 30000,
                "priority": "INTERACTIVE"
              }
            }
          }
        },
        "responses": {
          "201": {
            "description": "Session created successfully",
            "content": {
              "application/json": {
                "schema": {"$ref": "#/components/schemas/Session"}
              }
            }
          },
          "400": {"description": "Bad Request"},
          "401": {"description": "Unauthorized"},
          "429": {"description": "Rate Limit Exceeded"}
        }
      }
    }
  },
  "components": {
    "schemas": {
      "CreateSessionRequest": {
        "type": "object",
        "properties": {
          "persona_id": {"type": "string", "description": "Persona ID (default: family assistant)"},
          "timeout_ms": {"type": "integer", "description": "Session timeout in milliseconds", "minimum": 1000, "maximum": 300000, "default": 30000},
          "priority": {"type": "string", "description": "Priority level", "pattern": "^(URGENT|REALTIME|INTERACTIVE|BACKGROUND)$", "default": "INTERACTIVE"}
        },
        "example": {
          "persona_id": "persona_family_assistant",
          "timeout_ms": 30000,
          "priority": "INTERACTIVE"
        }
      },
      "Session": {
        "type": "object",
        "required": ["session_id", "user_id", "persona_id", "created_at", "status"],
        "properties": {
          "session_id": {"type": "string", "description": "Unique session identifier"},
          "user_id": {"type": "string", "description": "User who owns the session"},
          "persona_id": {"type": "string", "description": "Active persona"},
          "created_at": {"type": "string", "format": "date-time", "description": "ISO 8601 timestamp"},
          "status": {"type": "string", "enum": ["ACTIVE", "IDLE", "EXPIRED"], "description": "Session status"}
        }
      }
    },
    "securitySchemes": {
      "bearerAuth": {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": "JWT authentication (see ADR-0037)"
      }
    }
  }
}
```

#### 2. FlatBuffers Schema Annotations

**Approach:** Document FlatBuffers binary option in OpenAPI descriptions.

**Example:**

```python
@router.post(
    "/v1/sessions/{session_id}/turns",
    summary="Submit a turn",
    description="""
    Submit a user turn for AI processing.

    **Content-Type Options:**
    - `application/json`: JSON format (default, slower deserialization)
    - `application/flatbuffers`: FlatBuffers binary (faster, see ADR-0011)

    **FlatBuffers Schema:** `K1.REST.CreateTurnRequest`

    **Performance:** FlatBuffers 5× faster deserialization (<1ms vs 5ms JSON)

    **Note:** Clients must negotiate Content-Type and Accept headers.
    """,
    responses={
        201: {
            "description": "Turn created",
            "content": {
                "application/json": {"schema": {"$ref": "#/components/schemas/Turn"}},
                "application/flatbuffers": {"schema": {"type": "string", "format": "binary", "description": "FlatBuffers binary (K1.REST.Turn)"}}
            }
        }
    }
)
```

**Generated OpenAPI with FlatBuffers:**

```yaml
paths:
  /v1/sessions/{session_id}/turns:
    post:
      summary: Submit a turn
      description: |
        Submit a user turn for AI processing.

        **Content-Type Options:**
        - `application/json`: JSON format (default, slower deserialization)
        - `application/flatbuffers`: FlatBuffers binary (faster, see ADR-0011)

        **FlatBuffers Schema:** `K1.REST.CreateTurnRequest`

        **Performance:** FlatBuffers 5× faster deserialization (<1ms vs 5ms JSON)
      requestBody:
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateTurnRequest'
          application/flatbuffers:
            schema:
              type: string
              format: binary
              description: "FlatBuffers binary (K1.REST.CreateTurnRequest)"
```

#### 3. Swagger UI Configuration

**File:** `k1/api/rest/openapi_config.py`

```python
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

def custom_openapi(app: FastAPI):
    """Custom OpenAPI schema with K1 branding"""
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title="K1 Intelligence Module REST API",
        version="1.0.0",
        description="""
        # K1 Intelligence Module REST API

        Welcome to the K1 REST API documentation!

        ## Authentication

        All endpoints require JWT authentication (see ADR-0037):

        ```
        Authorization: Bearer <jwt_token>
        ```

        Get JWT token: `POST /v1/auth/token` with username/password.

        ## Rate Limits

        - 1,000 requests/hour per user (general)
        - 100 session creates/hour per user
        - 10,000 turns/hour per session

        Rate limit headers:
        - `RateLimit-Limit`: Quota
        - `RateLimit-Remaining`: Remaining quota
        - `RateLimit-Reset`: Reset timestamp

        ## FlatBuffers Binary Option

        K1 supports FlatBuffers binary serialization (see ADR-0011) for 5× faster deserialization:

        ```
        Content-Type: application/flatbuffers
        Accept: application/flatbuffers
        ```

        JSON is default (slower but easier to debug).

        ## Versioning

        K1 uses URL-based versioning:

        - `/v1/...`: Current stable version
        - `/v2/...`: Next version (when available)

        Deprecation notices will appear 90 days before removal.

        ## SDKs

        Generate client SDKs using OpenAPI Generator:

        ```bash
        # TypeScript
        openapi-generator-cli generate -i /v1/openapi.json -g typescript-axios -o ./sdk/typescript

        # Python
        openapi-generator-cli generate -i /v1/openapi.json -g python -o ./sdk/python

        # Go
        openapi-generator-cli generate -i /v1/openapi.json -g go -o ./sdk/go
        ```

        ## Support

        - Email: api-support@k1.example.com
        - Slack: #k1-api-support
        - Docs: https://docs.k1.example.com
        """,
        routes=app.routes,
        contact={
            "name": "K1 API Support",
            "email": "api-support@k1.example.com",
            "url": "https://docs.k1.example.com"
        },
        license_info={
            "name": "Proprietary",
            "url": "https://k1.example.com/license"
        },
        servers=[
            {"url": "https://api.k1.example.com", "description": "Production"},
            {"url": "https://staging-api.k1.example.com", "description": "Staging"},
            {"url": "http://localhost:8000", "description": "Development"}
        ]
    )

    # Add security schemes
    openapi_schema["components"]["securitySchemes"] = {
        "bearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "JWT authentication (see ADR-0037). Get token from POST /v1/auth/token"
        }
    }

    # Global security requirement
    openapi_schema["security"] = [{"bearerAuth": []}]

    app.openapi_schema = openapi_schema
    return app.openapi_schema

# Configure FastAPI app
app = FastAPI(
    title="K1 Intelligence Module REST API",
    version="1.0.0",
    docs_url="/docs",  # Swagger UI
    redoc_url="/redoc",  # ReDoc
    openapi_url="/v1/openapi.json"  # OpenAPI JSON
)

# Custom OpenAPI schema
app.openapi = lambda: custom_openapi(app)
```

#### 4. OpenAPI JSON + YAML Endpoints

```python
from fastapi import FastAPI
from fastapi.responses import Response
import yaml

@app.get("/v1/openapi.json", include_in_schema=False)
async def openapi_json():
    """OpenAPI spec in JSON format"""
    return app.openapi()

@app.get("/v1/openapi.yaml", include_in_schema=False)
async def openapi_yaml():
    """OpenAPI spec in YAML format"""
    openapi_json = app.openapi()
    openapi_yaml = yaml.dump(openapi_json, default_flow_style=False)
    return Response(content=openapi_yaml, media_type="application/x-yaml")
```

### Client SDK Generation

**TypeScript (axios):**
```bash
# Install OpenAPI Generator
npm install -g @openapitools/openapi-generator-cli

# Generate TypeScript client
openapi-generator-cli generate \
  -i https://api.k1.example.com/v1/openapi.json \
  -g typescript-axios \
  -o ./sdk/typescript \
  --additional-properties=npmName=@k1/rest-client,npmVersion=1.0.0

# Usage
import { SessionsApi, Configuration } from '@k1/rest-client';

const config = new Configuration({
  basePath: 'https://api.k1.example.com',
  accessToken: 'jwt_token_here'
});

const sessionsApi = new SessionsApi(config);
const session = await sessionsApi.createSession({
  personaId: 'persona_family_assistant',
  timeoutMs: 30000,
  priority: 'INTERACTIVE'
});
```

**Python:**
```bash
# Generate Python client
openapi-generator-cli generate \
  -i https://api.k1.example.com/v1/openapi.json \
  -g python \
  -o ./sdk/python \
  --additional-properties=packageName=k1_rest_client,projectName=k1-rest-client

# Usage
from k1_rest_client import ApiClient, Configuration, SessionsApi

config = Configuration(
    host='https://api.k1.example.com',
    access_token='jwt_token_here'
)

with ApiClient(config) as api_client:
    sessions_api = SessionsApi(api_client)
    session = sessions_api.create_session(
        create_session_request={
            'persona_id': 'persona_family_assistant',
            'timeout_ms': 30000,
            'priority': 'INTERACTIVE'
        }
    )
```

**Go:**
```bash
# Generate Go client
openapi-generator-cli generate \
  -i https://api.k1.example.com/v1/openapi.json \
  -g go \
  -o ./sdk/go \
  --additional-properties=packageName=k1client

# Usage
import (
    "context"
    k1 "github.com/example/k1-sdk-go"
)

config := k1.NewConfiguration()
config.Servers = k1.ServerConfigurations{
    {URL: "https://api.k1.example.com"},
}
config.AddDefaultHeader("Authorization", "Bearer jwt_token_here")

client := k1.NewAPIClient(config)
session, _, err := client.SessionsApi.CreateSession(context.Background()).CreateSessionRequest(k1.CreateSessionRequest{
    PersonaId: k1.PtrString("persona_family_assistant"),
    TimeoutMs: k1.PtrInt32(30000),
    Priority: k1.PtrString("INTERACTIVE"),
}).Execute()
```

### Performance Budgets

| Metric | Target | Notes |
|--------|--------|-------|
| **OpenAPI JSON Generation** | <50ms | Cached for 1 hour |
| **OpenAPI YAML Generation** | <100ms | Cached for 1 hour |
| **Swagger UI Load Time** | <2000ms | Static assets + OpenAPI fetch |
| **ReDoc Load Time** | <1500ms | Faster than Swagger UI |
| **SDK Generation Time** | <60s | TypeScript/Python/Go clients |

---

## Alternatives Considered

### Alternative 1: Manual Markdown Wiki ❌ REJECTED

**Approach:** Document REST API manually in Markdown wiki (separate from code).

**Pros:**
- Simple to start (just write Markdown)
- Full control over documentation format

**Cons:**
- ❌ Out-of-sync risk (90% stale in 6 months)
- ❌ No interactive testing (must use curl/Postman)
- ❌ No schema validation (examples don't enforce contracts)
- ❌ No SDK generation (manual client code)
- ❌ High maintenance (2-4 hours per feature update)

**Rejected because:** Manual documentation inevitably drifts from implementation, causing developer frustration and high support burden.

---

### Alternative 2: Postman Collections ❌ REJECTED

**Approach:** Maintain Postman collection with API requests + examples.

**Pros:**
- Interactive testing (Postman UI)
- Easy to share with team

**Cons:**
- ❌ Separate from code (drift risk)
- ❌ No schema validation at runtime
- ❌ Partial SDK generation (Postman codegen limited)
- ❌ Requires Postman account (not open standard)

**Rejected because:** Postman collections are proprietary format, separate from code (drift risk), and don't provide runtime schema validation or full SDK generation.

---

### Alternative 3: GraphQL Schema ❌ REJECTED

**Approach:** Use GraphQL instead of REST, introspection provides schema.

**Pros:**
- ✅ Always synchronized (introspection from schema)
- ✅ Interactive testing (GraphiQL playground)
- ✅ Schema validation (GraphQL type system)
- ✅ SDK generation (GraphQL codegen)

**Cons:**
- ❌ Major architectural change (REST → GraphQL)
- ❌ Over-fetching for simple CRUD (query complexity)
- ❌ No HTTP caching (POST /graphql for all requests)
- ❌ Learning curve for team (GraphQL vs REST)

**Rejected because:** GraphQL requires major architectural change (ADR-0041 chose REST), over-fetching overhead for simple CRUD operations, and team unfamiliar with GraphQL.

---

### Alternative 4: OpenAPI 3.1 Auto-Generated ✅ SELECTED

**Approach:** FastAPI + Pydantic models auto-generate OpenAPI 3.1 spec.

**Pros:**
- ✅ Always synchronized (generated from code)
- ✅ Interactive testing (Swagger UI, ReDoc)
- ✅ Schema validation (Pydantic models enforce at runtime)
- ✅ SDK generation (OpenAPI Generator for TypeScript/Python/Go)
- ✅ Low maintenance (zero manual updates)
- ✅ Industry standard (OpenAPI 3.1 supported by all tools)

**Cons:**
- FastAPI dependency (but already used per ADR-0041)
- Pydantic models required (but already used for validation)

**Selected because:** OpenAPI 3.1 auto-generation provides best balance of synchronization guarantee, interactive testing, schema validation, SDK generation, and low maintenance. FastAPI + Pydantic already used per ADR-0041.

---

### Alternative 5: gRPC Proto + grpc-gateway ❌ REJECTED

**Approach:** Define API in `.proto` files, generate OpenAPI from proto.

**Pros:**
- ✅ Synchronized (proto is source of truth)
- ✅ SDK generation (protoc generates clients)
- ✅ Schema validation (proto type system)

**Cons:**
- ❌ Major architectural change (REST → gRPC)
- ❌ Protobuf vs FlatBuffers (K1 standard is FlatBuffers per ADR-0011)
- ❌ grpc-gateway complexity (HTTP/JSON → gRPC translation)
- ❌ No browser support (gRPC-Web requires proxy)

**Rejected because:** gRPC requires major architectural change (ADR-0041 chose REST), uses Protobuf instead of K1 standard FlatBuffers, and adds grpc-gateway complexity.

---

## Consequences

### Positive Consequences

1. **Always Synchronized Documentation:** OpenAPI spec auto-generated from FastAPI code annotations (impossible to drift vs manual wiki 90% stale in 6 months)

2. **Interactive Testing:** Swagger UI at `/docs` provides live sandbox (try endpoints with JWT, see real responses) vs manual curl/Postman copy-paste

3. **Schema Validation:** Pydantic models enforce request/response contracts at runtime (400 Bad Request if invalid JSON) vs manual wiki examples don't enforce

4. **Rapid SDK Generation:** OpenAPI Generator creates TypeScript/Python/Go clients in 5 minutes (vs 3 days manual coding), always synchronized with API changes

5. **Low Maintenance:** Zero manual updates (OpenAPI spec auto-generated on every code change) vs manual wiki requires 2-4 hours per feature

6. **Developer Self-Service:** Developers can explore API, test endpoints, generate SDKs without support team intervention

### Negative Consequences

1. **FastAPI Dependency:** OpenAPI generation tightly coupled to FastAPI (migration to different framework requires rewrite)

2. **Pydantic Model Overhead:** All request/response types must be Pydantic models (adds boilerplate vs plain dictionaries)

3. **OpenAPI Generation Latency:** First request to `/v1/openapi.json` takes 50ms to generate (mitigation: 1-hour cache)

4. **Swagger UI Load Time:** Swagger UI requires 2000ms to load (static assets + OpenAPI fetch) vs instant manual wiki

### Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| **OpenAPI Spec Drift** | Low | High (breaks SDKs) | Automated tests validate OpenAPI spec matches implementation (CI/CD) |
| **Swagger UI Performance** | Low | Medium (slow docs) | Cache OpenAPI spec for 1 hour, use CDN for Swagger UI static assets |
| **SDK Generation Breaks** | Medium | High (client failures) | Test SDK generation in CI/CD, version lock OpenAPI Generator |
| **FlatBuffers Not Documented** | Medium | Low (confusion) | Add FlatBuffers annotations to OpenAPI descriptions + examples |
| **OpenAPI 3.1 Compatibility** | Low | Medium (tooling issues) | Use OpenAPI 3.1.0 (widely supported), test with OpenAPI Generator |

---

## Implementation Notes

### FastAPI Setup

```python
# k1/api/rest/main.py

from fastapi import FastAPI
from k1.api.rest.openapi_config import custom_openapi
from k1.api.rest import sessions, turns, conversations

app = FastAPI(
    title="K1 Intelligence Module REST API",
    version="1.0.0",
    docs_url="/docs",  # Swagger UI at /docs
    redoc_url="/redoc",  # ReDoc at /redoc
    openapi_url="/v1/openapi.json"  # OpenAPI JSON at /v1/openapi.json
)

# Custom OpenAPI schema
app.openapi = lambda: custom_openapi(app)

# Register routers
app.include_router(sessions.router)
app.include_router(turns.router)
app.include_router(conversations.router)
```

### OpenAPI Caching

```python
# k1/api/rest/openapi_cache.py

from fastapi import Request, Response
from functools import lru_cache
import time

# Cache OpenAPI spec for 1 hour
@lru_cache(maxsize=1)
def get_cached_openapi(timestamp: int):
    """Cache OpenAPI spec for 1 hour (timestamp rounded to hour)"""
    return app.openapi()

@app.get("/v1/openapi.json", include_in_schema=False)
async def openapi_json(request: Request):
    """OpenAPI spec with 1-hour cache"""
    # Round current time to hour
    current_hour = int(time.time() // 3600)

    # Get cached spec
    openapi_spec = get_cached_openapi(current_hour)

    # Return with Cache-Control header
    return Response(
        content=json.dumps(openapi_spec),
        media_type="application/json",
        headers={"Cache-Control": "public, max-age=3600"}  # 1 hour
    )
```

### CI/CD Validation

```yaml
# .github/workflows/openapi-validation.yml

name: OpenAPI Validation

on: [push, pull_request]

jobs:
  validate-openapi:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt

      - name: Generate OpenAPI spec
        run: |
          python -c "
          from k1.api.rest.main import app
          import json
          spec = app.openapi()
          with open('openapi.json', 'w') as f:
              json.dump(spec, f, indent=2)
          "

      - name: Validate OpenAPI spec
        uses: mbowman100/swagger-validator-action@master
        with:
          files: openapi.json

      - name: Generate TypeScript SDK (test)
        run: |
          npm install -g @openapitools/openapi-generator-cli
          openapi-generator-cli generate \
            -i openapi.json \
            -g typescript-axios \
            -o ./sdk-test/typescript

      - name: Test TypeScript SDK compiles
        run: |
          cd ./sdk-test/typescript
          npm install
          npm run build
```

---

## Migration Strategy

### Phase 1: OpenAPI Setup (Week 1)
- Add FastAPI + Pydantic models to existing endpoints
- Configure Swagger UI (`/docs`) and ReDoc (`/redoc`)
- Deploy to staging for team review

### Phase 2: Documentation Migration (Week 2)
- Migrate manual wiki documentation to OpenAPI descriptions
- Add FlatBuffers annotations to endpoint descriptions
- Validate OpenAPI spec in CI/CD

### Phase 3: SDK Generation (Week 3)
- Generate TypeScript, Python, Go SDKs with OpenAPI Generator
- Publish SDKs to npm (TypeScript), PyPI (Python), Go modules
- Update client documentation to use auto-generated SDKs

### Phase 4: Production Rollout (Week 4)
- Deploy OpenAPI endpoints to production
- Announce SDK availability to developers
- Deprecate manual wiki (redirect to `/docs`)

---

## Research Citations

1. **OpenAPI 3.1** — OpenAPI Initiative, 2021: *"Industry-standard API specification"*
2. **Swagger UI** — SmartBear, 2011: *"Interactive API documentation"*
3. **ReDoc** — Redocly, 2015: *"Clean API documentation from OpenAPI"*
4. **FastAPI** — Sebastián Ramírez, 2018: *"Modern Python web framework with automatic OpenAPI generation"*
5. **Pydantic** — Samuel Colvin, 2017: *"Data validation using Python type hints"*
6. **OpenAPI Generator** — OpenAPI Tools, 2018: *"Multi-language SDK generation from OpenAPI"*
7. **JSON Schema** — IETF, 2016: *"Schema validation for JSON"*
8. **REST** — Fielding, 2000: *"Architectural Styles and the Design of Network-based Software Architectures"*

---

## Appendix: OpenAPI 3.1 Features Used

| Feature | Purpose | Example |
|---------|---------|---------|
| **`operationId`** | Unique operation identifier for SDK generation | `create_session` |
| **`tags`** | Group endpoints by category | `["Sessions", "Turns", "Conversations"]` |
| **`summary`** | Short operation description (shown in Swagger UI) | `"Create a new session"` |
| **`description`** | Long operation description (Markdown supported) | `"Create a new K1 session for conversational AI interaction..."` |
| **`requestBody`** | Request schema (auto-generated from Pydantic model) | `CreateSessionRequest` |
| **`responses`** | Response schemas (auto-generated from Pydantic models) | `201: Session, 400: Error, 401: Unauthorized` |
| **`parameters`** | Path/query/header parameters (auto-detected from FastAPI) | `session_id: str` (path), `Authorization: str` (header) |
| **`security`** | Security requirements (JWT) | `[{"bearerAuth": []}]` |
| **`servers`** | API server URLs | `https://api.k1.example.com` (production) |
| **`components.schemas`** | Reusable schemas (Pydantic models) | `Session, Turn, Conversation` |
| **`components.securitySchemes`** | Security scheme definitions | `bearerAuth: JWT` |
| **`examples`** | Example requests/responses | `Config.schema_extra` in Pydantic models |

---

**End of ADR-0047**
