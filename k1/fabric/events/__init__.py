"""
k1.fabric.events -- Fabric event types and emitters.

Exports:
  - Topic constants (TOPIC_*)
  - Emitted event dataclasses
  - Consumed event dataclasses
  - EventEmitter wrapper
  - ProactiveGapDetector (5.4.4)
"""

from k1.fabric.events.event_emitter import EventEmitter, EventPort, ProactiveGapDetector
from k1.fabric.events.fabric_events import (  # -- Topic constants --; -- Emitted event dataclasses --; -- Consumed event dataclasses --
    CONSUMED_TOPICS,
    EMITTED_TOPICS,
    TOPIC_CAPABILITY_COMPLETED,
    TOPIC_CAPABILITY_FAILED,
    TOPIC_CAPABILITY_INVOKED,
    TOPIC_CAPABILITY_REGISTERED,
    TOPIC_CAPABILITY_UNREGISTERED,
    TOPIC_CONTRACT_UPDATED,
    TOPIC_CONTRACT_VALIDATION_FAILED,
    TOPIC_DISCOVERY_REQUEST,
    TOPIC_HEALTH_CHECK_REQUEST,
    TOPIC_LEARNING_SIGNAL,
    TOPIC_MCP_TOOL_DISCOVERED,
    TOPIC_OUTPUT_VALIDATION_FAILED,
    TOPIC_PRESSURE_SHEDDING,
    TOPIC_PRESSURE_WARNING,
    TOPIC_PROVIDER_HEALTH_CHANGED,
    TOPIC_STEP_EXECUTE,
    TOPIC_VERSION_CONFLICT,
    CapabilityCompletedEvent,
    CapabilityFailedEvent,
    CapabilityInvokedEvent,
    CapabilityRegisteredEvent,
    CapabilityUnregisteredEvent,
    ContractUpdatedEvent,
    ContractValidationFailedEvent,
    DiscoveryRequestEvent,
    HealthCheckRequestEvent,
    LearningSignalEvent,
    MCPToolDiscoveredEvent,
    OutputValidationFailedEvent,
    PressureSheddingEvent,
    PressureWarningEvent,
    ProviderHealthChangedEvent,
    StepExecuteEvent,
    VersionConflictEvent,
)

__all__ = [
    # Emitter + gap detection
    "EventEmitter",
    "EventPort",
    "ProactiveGapDetector",
    # Topic constants
    "EMITTED_TOPICS",
    "CONSUMED_TOPICS",
    "TOPIC_CAPABILITY_INVOKED",
    "TOPIC_CAPABILITY_COMPLETED",
    "TOPIC_CAPABILITY_FAILED",
    "TOPIC_LEARNING_SIGNAL",
    "TOPIC_CAPABILITY_REGISTERED",
    "TOPIC_CAPABILITY_UNREGISTERED",
    "TOPIC_VERSION_CONFLICT",
    "TOPIC_CONTRACT_VALIDATION_FAILED",
    "TOPIC_OUTPUT_VALIDATION_FAILED",
    "TOPIC_PROVIDER_HEALTH_CHANGED",
    "TOPIC_CONTRACT_UPDATED",
    "TOPIC_PRESSURE_WARNING",
    "TOPIC_PRESSURE_SHEDDING",
    "TOPIC_STEP_EXECUTE",
    "TOPIC_DISCOVERY_REQUEST",
    "TOPIC_HEALTH_CHECK_REQUEST",
    "TOPIC_MCP_TOOL_DISCOVERED",
    # Emitted event dataclasses
    "CapabilityInvokedEvent",
    "CapabilityCompletedEvent",
    "CapabilityFailedEvent",
    "LearningSignalEvent",
    "CapabilityRegisteredEvent",
    "CapabilityUnregisteredEvent",
    "VersionConflictEvent",
    "ContractValidationFailedEvent",
    "OutputValidationFailedEvent",
    "ProviderHealthChangedEvent",
    "ContractUpdatedEvent",
    "PressureWarningEvent",
    "PressureSheddingEvent",
    # Consumed event dataclasses
    "StepExecuteEvent",
    "DiscoveryRequestEvent",
    "HealthCheckRequestEvent",
    "MCPToolDiscoveredEvent",
]
