"""
poc.k1_poc.config -- Central YAML-based configuration for the POC.

All runtime-tunable knobs live in ``defaults.yaml`` and are exposed
through typed dataclasses in ``loader.py``.

Quick start::

    from poc.k1_poc.config import get_config
    cfg = get_config()
    cfg.actors.back.history_window   # -> 5
    cfg.bus.mailbox_capacity         # -> 64
"""

from poc.k1_poc.config.loader import (
    ActorsConfig,
    ArbiterConfig,
    BackActorConfig,
    BackPoolConfig,
    BusConfig,
    ColdTierConfig,
    DeltaConfig,
    EvictionConfig,
    ExperienceConfig,
    FrontActorConfig,
    FsmConfig,
    KernelConfig,
    LedgerConfig,
    LlmConfig,
    MigrationConfig,
    ObsAlertRuleConfig,
    ObsAlertsConfig,
    ObsConfig,
    ObsFsmConfig,
    ObsMetricsConfig,
    OrchestratorConfig,
    OverflowConfig,
    Phase1Config,
    PocConfig,
    PromptConfig,
    ProtocolsConfig,
    ReactConfig,
    ReconstructionConfig,
    SessionStateConfig,
    SessionStateSectionsConfig,
    SessionStateTiersConfig,
    StorageConfig,
    TaskConfig,
    ThrashConfig,
    ToolsConfig,
    WeavePolicyConfig,
    get_config,
    load_config,
    reset_config,
)

__all__ = [
    "ActorsConfig",
    "ArbiterConfig",
    "BackActorConfig",
    "BackPoolConfig",
    "BusConfig",
    "ColdTierConfig",
    "DeltaConfig",
    "EvictionConfig",
    "ExperienceConfig",
    "FrontActorConfig",
    "FsmConfig",
    "KernelConfig",
    "LedgerConfig",
    "LlmConfig",
    "MigrationConfig",
    "ObsAlertsConfig",
    "ObsAlertRuleConfig",
    "ObsConfig",
    "ObsFsmConfig",
    "ObsMetricsConfig",
    "OrchestratorConfig",
    "OverflowConfig",
    "Phase1Config",
    "PocConfig",
    "PromptConfig",
    "ProtocolsConfig",
    "ReactConfig",
    "ReconstructionConfig",
    "SessionStateConfig",
    "SessionStateSectionsConfig",
    "SessionStateTiersConfig",
    "StorageConfig",
    "TaskConfig",
    "ThrashConfig",
    "ToolsConfig",
    "WeavePolicyConfig",
    "get_config",
    "load_config",
    "reset_config",
]
