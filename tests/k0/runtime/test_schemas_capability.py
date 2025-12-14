"""
Tests for CapabilityProvider and CapabilityDefinition schema models.

Issue 1.1.2: Create CapabilityProvider Pydantic Model
ADR: ADR-K004 Capability Mesh Architecture
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from k0.runtime.schemas import (
    CapabilityDefinition,
    CapabilityProvider,
    FabricContextPolicy,
    ProviderType,
)


class TestProviderType:
    """Tests for ProviderType enum."""

    def test_provider_types_available(self):
        """Verify provider types are available."""
        assert ProviderType.MODULE == "module"
        assert ProviderType.PIPELINE == "pipeline"


class TestFabricContextPolicy:
    """Tests for FabricContextPolicy enum."""

    def test_context_policies_available(self):
        """Verify context policies are available."""
        assert FabricContextPolicy.INHERIT == "inherit"
        assert FabricContextPolicy.ISOLATED == "isolated"
        assert FabricContextPolicy.SYNTHETIC == "synthetic"


class TestCapabilityProviderModule:
    """Tests for module-type capability providers."""

    def test_capability_provider_module_valid(self):
        """Valid module provider with all required fields."""
        provider = CapabilityProvider(
            type=ProviderType.MODULE,
            module_id="salience.score:v1",
        )
        assert provider.type == ProviderType.MODULE
        assert provider.module_id == "salience.score:v1"
        assert provider.priority == 1  # default
        assert provider.condition == "always"  # default

    def test_capability_provider_module_with_priority(self):
        """Module provider with custom priority."""
        provider = CapabilityProvider(
            type=ProviderType.MODULE,
            module_id="salience.score:v1",
            priority=5,
        )
        assert provider.priority == 5

    def test_capability_provider_module_with_latency_budget(self):
        """Module provider with latency budget."""
        provider = CapabilityProvider(
            type=ProviderType.MODULE,
            module_id="salience.score:v1",
            latency_budget_ms=50,
        )
        assert provider.latency_budget_ms == 50

    def test_capability_provider_module_with_timeout(self):
        """Module provider with timeout."""
        provider = CapabilityProvider(
            type=ProviderType.MODULE,
            module_id="salience.score:v1",
            timeout_ms=100,
        )
        assert provider.timeout_ms == 100

    def test_capability_provider_module_missing_id_raises(self):
        """Module provider without module_id raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            CapabilityProvider(
                type=ProviderType.MODULE,
                # Missing module_id
            )
        assert "module_id required" in str(exc_info.value)

    def test_capability_provider_module_id_pattern(self):
        """Module ID must match pattern ^[a-z_]+\\.[a-z_]+(:[a-z0-9]+)?$."""
        # Valid without version
        provider = CapabilityProvider(
            type=ProviderType.MODULE,
            module_id="salience.score",
        )
        assert provider.module_id == "salience.score"

        # Valid with version
        provider = CapabilityProvider(
            type=ProviderType.MODULE,
            module_id="salience.score:v1",
        )
        assert provider.module_id == "salience.score:v1"

        # Invalid - uppercase
        with pytest.raises(ValidationError):
            CapabilityProvider(
                type=ProviderType.MODULE,
                module_id="Salience.Score:v1",
            )

    def test_capability_provider_priority_range(self):
        """Priority must be between 1 and 100."""
        # Valid min
        provider = CapabilityProvider(
            type=ProviderType.MODULE,
            module_id="salience.score:v1",
            priority=1,
        )
        assert provider.priority == 1

        # Valid max
        provider = CapabilityProvider(
            type=ProviderType.MODULE,
            module_id="salience.score:v1",
            priority=100,
        )
        assert provider.priority == 100

        # Invalid - too low
        with pytest.raises(ValidationError):
            CapabilityProvider(
                type=ProviderType.MODULE,
                module_id="salience.score:v1",
                priority=0,
            )

        # Invalid - too high
        with pytest.raises(ValidationError):
            CapabilityProvider(
                type=ProviderType.MODULE,
                module_id="salience.score:v1",
                priority=101,
            )


class TestCapabilityProviderPipeline:
    """Tests for pipeline-type capability providers."""

    def test_capability_provider_pipeline_valid(self):
        """Valid pipeline provider with all required fields."""
        provider = CapabilityProvider(
            type=ProviderType.PIPELINE,
            pipeline_id="P03_CONSOLIDATION",
            request_topic="fabric.consolidation.request.v1",
            response_topic="fabric.consolidation.response.v1",
        )
        assert provider.type == ProviderType.PIPELINE
        assert provider.pipeline_id == "P03_CONSOLIDATION"
        assert provider.request_topic == "fabric.consolidation.request.v1"
        assert provider.response_topic == "fabric.consolidation.response.v1"

    def test_capability_provider_pipeline_missing_id_raises(self):
        """Pipeline provider without pipeline_id raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            CapabilityProvider(
                type=ProviderType.PIPELINE,
                request_topic="fabric.request.v1",
                response_topic="fabric.response.v1",
                # Missing pipeline_id
            )
        assert "pipeline_id required" in str(exc_info.value)

    def test_capability_provider_pipeline_missing_topics_raises(self):
        """Pipeline provider without topics raises ValidationError."""
        # Missing request_topic
        with pytest.raises(ValidationError) as exc_info:
            CapabilityProvider(
                type=ProviderType.PIPELINE,
                pipeline_id="P03_CONSOLIDATION",
                response_topic="fabric.response.v1",
                # Missing request_topic
            )
        assert "request_topic and response_topic required" in str(exc_info.value)

        # Missing response_topic
        with pytest.raises(ValidationError) as exc_info:
            CapabilityProvider(
                type=ProviderType.PIPELINE,
                pipeline_id="P03_CONSOLIDATION",
                request_topic="fabric.request.v1",
                # Missing response_topic
            )
        assert "request_topic and response_topic required" in str(exc_info.value)


class TestCapabilityDefinition:
    """Tests for CapabilityDefinition."""

    def test_capability_definition_valid(self):
        """Valid capability definition with providers."""
        definition = CapabilityDefinition(
            description="Compute salience score for memory items",
            providers=[
                CapabilityProvider(
                    type=ProviderType.MODULE,
                    module_id="salience.score:v1",
                ),
            ],
        )
        assert definition.description == "Compute salience score for memory items"
        assert len(definition.providers) == 1
        assert definition.default_timeout_ms == 100  # default

    def test_capability_definition_multiple_providers(self):
        """Capability definition with multiple providers (priority ordering)."""
        definition = CapabilityDefinition(
            description="Retrieve similar memories",
            providers=[
                CapabilityProvider(
                    type=ProviderType.MODULE,
                    module_id="retrieval.faiss:v1",
                    priority=1,
                ),
                CapabilityProvider(
                    type=ProviderType.MODULE,
                    module_id="retrieval.brute_force:v1",
                    priority=10,
                ),
            ],
        )
        assert len(definition.providers) == 2
        assert definition.providers[0].priority == 1
        assert definition.providers[1].priority == 10

    def test_capability_definition_custom_timeout(self):
        """Capability definition with custom timeout."""
        definition = CapabilityDefinition(
            description="Long-running analysis",
            providers=[
                CapabilityProvider(
                    type=ProviderType.MODULE,
                    module_id="analysis.deep:v1",
                ),
            ],
            default_timeout_ms=5000,
        )
        assert definition.default_timeout_ms == 5000

    def test_capability_definition_empty_providers_raises(self):
        """Capability definition with empty providers raises ValidationError."""
        with pytest.raises(ValidationError):
            CapabilityDefinition(
                description="No providers",
                providers=[],
            )

    def test_capability_definition_timeout_range(self):
        """Default timeout must be between 1 and 60000."""
        # Valid min
        definition = CapabilityDefinition(
            description="Fast",
            providers=[
                CapabilityProvider(
                    type=ProviderType.MODULE,
                    module_id="fast.module:v1",
                ),
            ],
            default_timeout_ms=1,
        )
        assert definition.default_timeout_ms == 1

        # Valid max
        definition = CapabilityDefinition(
            description="Slow",
            providers=[
                CapabilityProvider(
                    type=ProviderType.MODULE,
                    module_id="slow.module:v1",
                ),
            ],
            default_timeout_ms=60000,
        )
        assert definition.default_timeout_ms == 60000

        # Invalid - too low
        with pytest.raises(ValidationError):
            CapabilityDefinition(
                description="Too fast",
                providers=[
                    CapabilityProvider(
                        type=ProviderType.MODULE,
                        module_id="module:v1",
                    ),
                ],
                default_timeout_ms=0,
            )

        # Invalid - too high
        with pytest.raises(ValidationError):
            CapabilityDefinition(
                description="Too slow",
                providers=[
                    CapabilityProvider(
                        type=ProviderType.MODULE,
                        module_id="module:v1",
                    ),
                ],
                default_timeout_ms=60001,
            )
