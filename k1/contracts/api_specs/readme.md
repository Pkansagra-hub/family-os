# API Specification Contracts

**Source ADR:** ADR-0047

## Overview

This directory contains OpenAPI 3.1 specifications for all K1 REST APIs, ensuring consistent API design and documentation.

## Contracts Included

### 1. OpenAPI 3.1 Master Specification (`openapi_3_1_specs/master_spec.yaml`)
- Complete K1 API specification
- All endpoints documented
- Schema definitions
- Security schemes

### 2. Endpoint Versioning Contract (`endpoint_versioning.yaml`)
- API versioning strategy
- URL versioning format (`/v1/`, `/v2/`)
- Deprecation policy (90-day notice)
- Version compatibility matrix

### 3. Error Response Contract (`error_responses.yaml`)
- RFC 7807 Problem Details format
- Error code taxonomy
- Error response schemas
- Error handling guidelines

## Key Specifications

### OpenAPI 3.1 Structure
```yaml
openapi: 3.1.0
info:
  title: K1 Intelligence Module API
  version: 1.0.0
  description: K1 real-time agentic orchestration API

servers:
  - url: https://api.k1.local/v1
    description: Local K1 instance

paths:
  /sessions:
    post:
      summary: Create new session
      operationId: createSession
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/SessionCreate'
      responses:
        '201':
          description: Session created
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Session'
```

### Versioning Strategy
```yaml
versioning:
  strategy: url_path
  format: /v{major}/
  current_version: v1
  supported_versions:
    - v1
  deprecated_versions: []
  deprecation_notice_period_days: 90
```

### Error Response Format (RFC 7807)
```yaml
error:
  type: string           # URI reference identifying problem type
  title: string          # Short, human-readable summary
  status: integer        # HTTP status code
  detail: string         # Detailed error explanation
  instance: string       # URI reference to specific occurrence
  trace_id: string       # cognitive_trace_id for debugging
```

## OpenAPI Specifications Directory

The `openapi_3_1_specs/` directory contains:

- `master_spec.yaml` - Complete API specification
- `sessions_api.yaml` - Session management endpoints
- `turns_api.yaml` - Turn management endpoints
- `agents_api.yaml` - Agent management endpoints
- `tools_api.yaml` - Tool invocation endpoints
- `schemas/` - Reusable schema definitions
- `examples/` - Request/response examples

## Usage

### Generate API Documentation
```bash
# Generate HTML documentation from OpenAPI spec
npx @redocly/cli build-docs openapi_3_1_specs/master_spec.yaml \
  --output docs/api/index.html
```

### Validate OpenAPI Spec
```bash
# Validate spec against OpenAPI 3.1 schema
npx @redocly/cli lint openapi_3_1_specs/master_spec.yaml
```

### Generate Client SDKs
```bash
# Generate TypeScript client
openapi-generator generate \
  -i openapi_3_1_specs/master_spec.yaml \
  -g typescript-axios \
  -o clients/typescript
```

## Related Contracts

- REST API Contracts: `../api/rest/`
- WebSocket Contracts: `../api/websocket/`
- FlatBuffers Schemas: `../flatbuffers/`

---

**Last Updated:** 2025-10-13
