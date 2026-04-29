"""k1.model_hub -- Model Hub module package facade.

Re-exports public types, ports, config, events, and errors so that
consumers can import from ``k1.model_hub`` directly.

Import graph
------------
k1.model_hub
  -> k1.model_hub.types      (domain types, enums, errors)
  -> k1.model_hub.config     (ModelHubConfig)
  -> k1.model_hub.events     (topic constants, payload dataclasses)
  -> k1.model_hub.ports      (7 port protocols)

References
----------
- model_hub.mmd: Architecture spec
- ADR-0001b: Model Hub Architecture & LLM Integration
"""

# -- Config (source of truth: k1/model_hub/config.py [F02]) --
from k1.model_hub.config import ModelHubConfig  # noqa: F401

# -- Events (source of truth: k1/model_hub/events.py [F04]) --
from k1.model_hub.events import (  # noqa: F401
    TOPIC_CACHE_HIT,
    TOPIC_CAPABILITY_AVAILABLE,
    TOPIC_CIRCUIT_STATE,
    TOPIC_FALLBACK_TRIGGERED,
    TOPIC_PROVIDER_FAILURE,
    TOPIC_PROVIDER_HEALTH,
    TOPIC_PROVIDER_REGISTERED,
    TOPIC_REQUEST_RECEIVED,
    TOPIC_REQUEST_ROUTED,
    TOPIC_RESPONSE_COMPLETE,
)

# -- Manifest (source of truth: k1/model_hub/manifest.py [F03]) --
from k1.model_hub.manifest import ModelSpec, ProviderManifest  # noqa: F401

# -- Ports (source of truth: k1/model_hub/ports/__init__.py [F09]) --
from k1.model_hub.ports import (  # noqa: F401
    IConfigPort,
    ICredentialPort,
    IEventPort,
    IHealthPort,
    IMetricsPort,
    IModelHubPort,
    IStateReadPort,
)

# -- Domain types (source of truth: k1/model_hub/types.py [F01]) --
from k1.model_hub.types import (  # noqa: F401; Enums; Conversation primitives; Core types; Health; Errors
    CapabilityType,
    CircuitOpenError,
    CircuitState,
    FinishReason,
    HealthStatus,
    HubChunk,
    HubHealthReport,
    HubRequest,
    HubResponse,
    HubTimeoutError,
    Message,
    ModelHubError,
    ModelInfo,
    ModelPreference,
    ModelTier,
    NoEligibleProviderError,
    PlacementType,
    Priority,
    ProviderError,
    ProviderHealthStatus,
    RateLimitError,
    RequestConstraints,
    ResponseMetadata,
    TokenUsage,
    ToolCallResult,
    ToolDefinition,
    ValidationError,
)
