# Config Module

## Overview

The **config** module contains static YAML configuration files shipped with the K0 kernel. These configurations define runtime settings, observability parameters, external service connections, and operational defaults across all K0 subsystems.

## Purpose

- **Centralized Configuration**: Single source of truth for kernel settings across environments
- **External Services**: Configure Neo4j, embedding backends, and other external dependencies
- **Environment Management**: Support development, staging, and production configurations
- **Observability**: Define logging, metrics, tracing, and telemetry parameters
- **Performance Budgets**: Codify latency targets and QoS policies

## Configuration Files

### 1. `kernel.yaml` - Core Kernel Settings

Primary configuration for K0 runtime server, QoS scheduler, security, and telemetry.

**Sections:**

- **`version`** - Semantic version of configuration schema
- **`environment`** - Deployment environment (development, staging, production)
- **`server`** - FastAPI/ASGI server settings
  - `host` - Bind address (default: `0.0.0.0`)
  - `port` - Bind port (default: `8080`)
  - `log_level` - Logging verbosity (info, debug, warning, error)
  - `timeout_graceful_shutdown` - Graceful shutdown timeout in seconds (default: `30`)
- **`retention`** - Data retention policies
  - `wal_days` - WAL retention window (default: 7 days)
  - `wal_max_events` - Max WAL events before rotation (default: 10M)
- **`qos`** - Quality of Service scheduler settings
  - `scheduler_profile` - Profile name: `balanced`, `high-throughput`, `low-latency` (default: `balanced`)
- **`security`** - Security and key rotation settings
  - `key_rotation_grace_window_hours` - Grace period for old keys (default: 24 hours)
  - `key_rotation_max_grace_hours` - Maximum allowed grace period (default: 168 hours = 1 week)
- **`telemetry`** - Observability and metrics settings
  - `otlp_endpoint` - OpenTelemetry collector endpoint (null = disabled)
  - `prometheus_enabled` - Enable Prometheus metrics export (default: true)

**Example:**

```yaml
version: 0.0.0-dev
environment: production
server:
  host: "0.0.0.0"
  port: 8080
  log_level: info
qos:
  scheduler_profile: balanced
security:
  key_rotation_grace_window_hours: 72
telemetry:
  otlp_endpoint: "http://otel-collector:4317"
  prometheus_enabled: true
```

### 2. `logging.yaml` - Structured Logging Configuration

Python `logging` module configuration (compatible with `logging.config.dictConfig`).

**Sections:**

- **`version`** - Config schema version (always `1`)
- **`formatters`** - Log format definitions
  - `structured` - Timestamped structured format
- **`handlers`** - Log output handlers
  - `console` - Stdout handler with structured formatter
- **`root`** - Root logger configuration
  - `level` - Default log level (INFO)
  - `handlers` - List of enabled handlers

**Example:**

```yaml
version: 1
formatters:
  structured:
    format: "%(asctime)s %(levelname)s %(name)s %(message)s"
handlers:
  console:
    class: logging.StreamHandler
    level: INFO
    formatter: structured
    stream: ext://sys.stdout
root:
  level: INFO
  handlers: [console]
```

### 3. `neo4j.yaml` - Neo4j Knowledge Graph Configuration

Comprehensive configuration for Neo4j graph database driver (related to ADR-0081).

**Sections:**

- **`connection`** - Bolt protocol connection settings
  - `uri` - Neo4j URI (e.g., `neo4j://localhost:7687`)
  - `auth.username` / `auth.password` - Credentials
  - `max_connection_pool_size` - Connection pool limit (default: 100)
  - `encrypted` - TLS/SSL enabled (default: false for dev)

- **`database`** - Neo4j database settings
  - `name` - Database name (default: `neo4j`)
  - `default_transaction_timeout_seconds` - Transaction timeout (default: 30s)
  - `max_retry_time_seconds` - Retry window for transient failures (default: 30s)

- **`query`** - Query performance tuning
  - `fetch_size` - Records per batch (default: 1000)
  - `max_results_default` - Default result limit (default: 100)
  - `temporal_snapshot_enabled` - Enable `as_of` timestamp queries (default: true)

- **`schema`** - Temporal graph schema (ADR-0081a)
  - `node_labels` - Entity types (Person, Location, Event, Organization, Thing)
  - `relationship_types` - 50+ relationship types (family, social, employment, location, etc.)
  - `temporal_properties` - Versioning fields (valid_from, valid_to, confidence, created_at, updated_at)

- **`performance`** - Query latency budgets (P95 targets)
  - `entity_lookup_p95_ms: 10` - Entity lookup by ID
  - `relationship_query_p95_ms: 30` - Relationship query (1 hop)
  - `shortest_path_p95_ms: 100` - Shortest path (depth 6)
  - `insert_entity_p95_ms: 20` - Entity write latency

- **`privacy`** - Privacy band integration (ADR-0081a)
  - `privacy_bands` - GREEN (shareable), AMBER (personal), RED (sensitive)
  - `redact_pii_enabled` - PII redaction for RED band entities
  - `audit_enabled` - Audit logging for sensitive operations

- **`docker`** - Docker Compose settings for local development
  - Neo4j container configuration with memory limits

**Example:**

```yaml
connection:
  uri: "neo4j://localhost:7687"
  auth:
    username: "neo4j"
    password: "${NEO4J_PASSWORD}"
database:
  name: "familyos"
privacy:
  privacy_bands: ["GREEN", "AMBER", "RED"]
  redact_pii_enabled: true
```

### 4. `embeddings.yml` - Embedding Backend Configuration

Configuration for async embedding workers (sentence-transformers, OpenAI, Ollama, fake).

**Sections:**

- **`default_backend`** - Active backend: `sentence-transformers`, `openai`, `ollama`, `fake`

- **`backends`** - Backend-specific settings
  - **`sentence-transformers`** - Local HuggingFace models
    - `model` - Model name (e.g., `all-mpnet-base-v2` for 768 dims)
    - `device` - CPU or CUDA
    - `batch_size` - Batch multiple texts for efficiency (default: 32)
    - `normalize_embeddings` - L2 normalization (default: true)
  - **`openai`** - OpenAI API
    - `model` - `text-embedding-3-small` (1536 dims) or `text-embedding-3-large` (3072 dims)
    - `rate_limit_rpm` - Requests per minute (Tier 1: 3000)
    - `rate_limit_tpm` - Tokens per minute (Tier 1: 1M)
    - `retry_max_attempts` - Retry count (default: 3)
  - **`ollama`** - Local Ollama deployment
    - `url` - Ollama server URL (default: `http://localhost:11434`)
    - `model` - Model name (e.g., `llama2`, `mistral`)
  - **`fake`** - Deterministic hash-based embeddings (testing only)
    - `dimension` - Embedding dimension (default: 384)

- **`worker`** - Embedding worker settings
  - `batch_size` - Process N outbox entries per `run_once()` (default: 10)
  - `poll_interval_sec` - Outbox polling frequency (default: 1.0s)
  - `max_retries` - Retry attempts for failed embeddings (default: 3)

- **`performance`** - Latency targets
  - `target_latency_ms: 100` - Single embedding computation
  - `batch_target_latency_ms: 500` - Batch of 10 embeddings

- **`observability`** - Logging and metrics
  - `log_level` - Logging verbosity (default: INFO)
  - `metrics_enabled` - Prometheus metrics (default: true)
  - `emit_embedding_vector` - Log full vectors (expensive, debugging only)

**Example:**

```yaml
default_backend: "sentence-transformers"
backends:
  sentence-transformers:
    model: "all-mpnet-base-v2"
    device: "cpu"
    batch_size: 32
worker:
  batch_size: 10
  poll_interval_sec: 1.0
```

## Loading Configurations

### Programmatic Access

```python
from k0.config import KERNEL_CONFIG_PATH, LOGGING_CONFIG_PATH
from k0.kernel.config import KernelSettings
import yaml

# Load kernel settings (Pydantic model with validation)
settings = KernelSettings.load(config_path=KERNEL_CONFIG_PATH)

# Load raw YAML
with open(KERNEL_CONFIG_PATH) as f:
    config = yaml.safe_load(f)
```

### CLI Overrides

The `k0ctl` CLI supports configuration overrides via `--config` and `--set`:

```bash
# Use custom config file
k0ctl --config config/prod.yaml serve

# Override specific values
k0ctl --set server.port=9090 --set qos.scheduler_profile=high-throughput serve

# Multiple overrides
k0ctl --set server.host=127.0.0.1 --set telemetry.otlp_endpoint=http://collector:4317 serve
```

### Environment Variables

Some configurations support environment variable substitution (e.g., `${NEO4J_PASSWORD}`):

```bash
export NEO4J_PASSWORD="secure-password"
k0ctl serve  # neo4j.yaml will resolve ${NEO4J_PASSWORD}
```

## Configuration Validation

**Kernel Settings** are validated via Pydantic models (`KernelSettings`):

```python
from k0.kernel.config import KernelSettings

try:
    settings = KernelSettings.load(config_path="config/kernel.yaml")
except Exception as e:
    print(f"Invalid configuration: {e}")
```

**Neo4j Configuration** is validated at driver initialization:

```python
from k0.drivers.neo4j_driver import Neo4jKGDriver

driver = Neo4jKGDriver(
    uri="neo4j://localhost:7687",
    username="neo4j",
    password="test-password",
)
driver.connect()  # Raises Neo4jError if connection fails
```

## Package Constants

The `__init__.py` exports key constants for programmatic access:

- **`PACKAGE_ROOT`** - Path to `k0/config/` directory
- **`KERNEL_CONFIG_PATH`** - Path to `kernel.yaml`
- **`LOGGING_CONFIG_PATH`** - Path to `logging.yaml`

```python
from k0.config import KERNEL_CONFIG_PATH, LOGGING_CONFIG_PATH
print(KERNEL_CONFIG_PATH)  # /path/to/k0/config/kernel.yaml
```

## Integration Points

### With Kernel Runtime

```python
from k0.kernel.config import KernelSettings
from k0.kernel.main import run as run_kernel

settings = KernelSettings.load()
run_kernel(settings, host=settings.server.host, port=settings.server.port)
```

### With Observability

```python
from k0.obs import configure_structured_logging
from k0.config import LOGGING_CONFIG_PATH
import yaml

with open(LOGGING_CONFIG_PATH) as f:
    logging_config = yaml.safe_load(f)

import logging.config
logging.config.dictConfig(logging_config)
```

### With Driver Layer

```python
from k0.drivers.neo4j_driver import Neo4jKGDriver
import yaml

with open("k0/config/neo4j.yaml") as f:
    neo4j_config = yaml.safe_load(f)

driver = Neo4jKGDriver(
    uri=neo4j_config["connection"]["uri"],
    username=neo4j_config["connection"]["auth"]["username"],
    password=neo4j_config["connection"]["auth"]["password"],
)
```

## Best Practices

1. **Environment-Specific Configs**: Maintain separate files for dev/staging/prod
2. **Secret Management**: Use environment variables for passwords and API keys
3. **Version Control**: Track config schemas with semantic versioning
4. **Validation**: Always validate configs at startup to fail fast
5. **Documentation**: Comment YAML files extensively for maintainability
6. **Defaults**: Provide sensible defaults for optional parameters

## Related Modules

- **k0.kernel.config**: Pydantic models for kernel settings validation
- **k0.cli**: CLI integration with config overrides
- **k0.drivers**: Driver implementations using config files
- **k0.obs**: Observability configuration (logging, metrics, tracing)
- **k0.qos**: Scheduler profile selection from config
