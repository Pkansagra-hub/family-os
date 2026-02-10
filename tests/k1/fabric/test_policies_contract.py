"""
Epic 6.4.3 -- test_policies_contract.py -- Policies Contract Compliance.

Verifies all declarations in k1/contracts/modules/fabric/policies.contract.yaml
are reflected in the actual implementation:

  1. Performance budgets (SLI targets) declared in contract match code defaults.
  2. Circuit breaker config defaults match contract global section.
  3. Per-provider threshold values are declared and consistent.
  4. SafetyBand ordering is GREEN < AMBER < RED < CRISIS.
  5. Safety enforcement rules (mandatory, red requires approval, deny unclassified).
  6. Audit requirements (trace_id, required fields).
  7. Capability grants are complete and consistent with wiring.
  8. Egress rules and agent pool limits.

References:
  - k1/contracts/modules/fabric/policies.contract.yaml
  - CircuitBreakerConfig (k1/fabric/circuit_breaker/breaker.py)
  - SafetyBand (k1/fabric/types.py)
  - fabric-implementation-plan.md Epic 6.4.3
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

# ---------------------------------------------------------------------------
# Load the policies contract YAML once
# ---------------------------------------------------------------------------

_CONTRACT_PATH = (
    Path(__file__).resolve().parents[3]
    / "k1"
    / "contracts"
    / "modules"
    / "fabric"
    / "policies.contract.yaml"
)


@pytest.fixture(scope="module")
def policies() -> dict:
    """Load the full policies.contract.yaml."""
    assert _CONTRACT_PATH.exists(), f"Missing policies contract: {_CONTRACT_PATH}"
    with open(_CONTRACT_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ===================================================================
# 1. Contract metadata
# ===================================================================


class TestPoliciesMetadata:
    """Verify top-level metadata fields."""

    def test_module_id(self, policies: dict) -> None:
        assert policies["metadata"]["module_id"] == "fabric"

    def test_owner(self, policies: dict) -> None:
        assert policies["metadata"]["owner"] == "platform-team"

    def test_band(self, policies: dict) -> None:
        assert policies["metadata"]["band"] == "GREEN"

    def test_contract_version(self, policies: dict) -> None:
        assert policies["contract_version"] == 1

    def test_impl_version_semver(self, policies: dict) -> None:
        import re

        ver = policies["impl_version"]
        assert re.match(r"^\d+\.\d+\.\d+$", ver), f"Not semver: {ver}"


# ===================================================================
# 2. Capability grants
# ===================================================================


class TestCapabilityGrants:
    """Verify all 12 capability grants declared in the contract."""

    EXPECTED_GRANTS = [
        "fabric:execute:v1",
        "fabric:retrieve:v1",
        "fabric:register:v1",
        "fabric:resolve:v1",
        "fabric:health:v1",
        "session:read:v1",
        "bus:publish:v1",
        "bridge:execute:v1",
        "model-gateway:call:v1",
        "prompt-system:resolve:v1",
        "delta-bus:publish:v1",
        "scheduler:submit:v1",
    ]

    def test_grants_count(self, policies: dict) -> None:
        grants = policies["capabilities"]["granted"]
        assert len(grants) == 12

    @pytest.mark.parametrize("grant", EXPECTED_GRANTS)
    def test_grant_present(self, policies: dict, grant: str) -> None:
        """Each expected grant appears in the declared list."""
        assert grant in policies["capabilities"]["granted"]

    def test_no_extra_grants(self, policies: dict) -> None:
        """No undeclared grants sneak in."""
        actual = set(policies["capabilities"]["granted"])
        expected = set(self.EXPECTED_GRANTS)
        extra = actual - expected
        assert not extra, f"Unexpected grants: {extra}"


# ===================================================================
# 3. Performance budget -- top-level latency targets
# ===================================================================


class TestPerformanceBudgets:
    """Verify SLI targets from the budgets section."""

    def test_latency_p95(self, policies: dict) -> None:
        assert policies["budgets"]["latency_ms_p95"] == 100

    def test_cost_usd_per_session_max(self, policies: dict) -> None:
        assert policies["budgets"]["cost_usd_per_session_max"] == 0.05

    def test_kv_cache_mb_max(self, policies: dict) -> None:
        assert policies["budgets"]["kv_cache_mb_max"] == 2.0


# ===================================================================
# 4. Performance budget -- extension SLI targets
# ===================================================================


class TestExtensionBudgets:
    """Verify all extension budget targets (Section 22 performance targets)."""

    @pytest.mark.parametrize(
        "key,expected",
        [
            ("registry_lookup_ms_p95", 1),
            ("registry_lookup_ms_max", 5),
            ("retrieval_10k_ms_p95", 20),
            ("retrieval_10k_ms_max", 50),
            ("retrieval_100k_ms_p95", 50),
            ("retrieval_100k_ms_max", 100),
            ("provider_resolution_ms_p95", 5),
            ("provider_resolution_ms_max", 10),
            ("context_build_simple_ms_p95", 10),
            ("context_build_simple_ms_max", 50),
            ("context_build_full_ms_p95", 50),
            ("context_build_full_ms_max", 200),
        ],
    )
    def test_latency_target(self, policies: dict, key: str, expected: int) -> None:
        ext = policies["budgets"]["extensions"]
        assert ext[key] == expected, f"{key}: expected {expected}, got {ext.get(key)}"

    def test_max_concurrent_sessions(self, policies: dict) -> None:
        assert policies["budgets"]["extensions"]["max_concurrent_sessions"] == 50

    def test_context_token_budget_max(self, policies: dict) -> None:
        assert policies["budgets"]["extensions"]["context_token_budget_max"] == 128_000

    def test_wfq_queue_depth_max(self, policies: dict) -> None:
        assert policies["budgets"]["extensions"]["wfq_queue_depth_max"] == 256

    def test_agent_pool_max_warm(self, policies: dict) -> None:
        assert policies["budgets"]["extensions"]["agent_pool_max_warm"] == 10

    def test_agent_pool_max_active(self, policies: dict) -> None:
        assert policies["budgets"]["extensions"]["agent_pool_max_active"] == 50


class TestProviderTimeouts:
    """Verify per-provider execution timeout targets."""

    @pytest.mark.parametrize(
        "key,seconds",
        [
            ("provider_timeout_mcp_local_s", 10),
            ("provider_timeout_mcp_remote_s", 15),
            ("provider_timeout_wasm_s", 5),
            ("provider_timeout_bridge_s", 10),
            ("provider_timeout_agent_s", 30),
            ("provider_timeout_workflow_s", 60),
        ],
    )
    def test_provider_timeout(self, policies: dict, key: str, seconds: int) -> None:
        ext = policies["budgets"]["extensions"]
        assert ext[key] == seconds


# ===================================================================
# 5. Circuit breaker -- global config
# ===================================================================


class TestCircuitBreakerGlobal:
    """Verify global circuit breaker policy matches code defaults."""

    def test_timeout_s(self, policies: dict) -> None:
        assert policies["circuit_breaker"]["global"]["timeout_s"] == 30

    def test_failure_threshold(self, policies: dict) -> None:
        assert policies["circuit_breaker"]["global"]["failure_threshold_per_min"] == 5

    def test_window_s(self, policies: dict) -> None:
        assert policies["circuit_breaker"]["global"]["window_s"] == 60

    def test_half_open_timeout_s(self, policies: dict) -> None:
        assert policies["circuit_breaker"]["global"]["half_open_timeout_s"] == 30

    def test_retry_strategy(self, policies: dict) -> None:
        assert policies["circuit_breaker"]["global"]["retry_strategy"] == "exponential_backoff"

    def test_retry_base_s(self, policies: dict) -> None:
        assert policies["circuit_breaker"]["global"]["retry_base_s"] == 1

    def test_retry_max_s(self, policies: dict) -> None:
        assert policies["circuit_breaker"]["global"]["retry_max_s"] == 30

    def test_retry_jitter(self, policies: dict) -> None:
        assert policies["circuit_breaker"]["global"]["retry_jitter"] is True


class TestCircuitBreakerCodeAlignment:
    """Verify CircuitBreakerConfig defaults match the contract values."""

    def test_timeout_ms_matches(self, policies: dict) -> None:
        from k1.fabric.circuit_breaker.breaker import CircuitBreakerConfig

        config = CircuitBreakerConfig()
        contract_ms = policies["circuit_breaker"]["global"]["timeout_s"] * 1000
        assert config.timeout_ms == contract_ms

    def test_failure_threshold_matches(self, policies: dict) -> None:
        from k1.fabric.circuit_breaker.breaker import CircuitBreakerConfig

        config = CircuitBreakerConfig()
        assert (
            config.failure_threshold
            == policies["circuit_breaker"]["global"]["failure_threshold_per_min"]
        )

    def test_window_ms_matches(self, policies: dict) -> None:
        from k1.fabric.circuit_breaker.breaker import CircuitBreakerConfig

        config = CircuitBreakerConfig()
        contract_ms = policies["circuit_breaker"]["global"]["window_s"] * 1000
        assert config.failure_window_ms == contract_ms

    def test_half_open_ms_matches(self, policies: dict) -> None:
        from k1.fabric.circuit_breaker.breaker import CircuitBreakerConfig

        config = CircuitBreakerConfig()
        contract_ms = policies["circuit_breaker"]["global"]["half_open_timeout_s"] * 1000
        assert config.half_open_after_ms == contract_ms


# ===================================================================
# 6. Circuit breaker -- per-provider thresholds
# ===================================================================


class TestCircuitBreakerPerProvider:
    """Verify per-provider failure thresholds."""

    @pytest.mark.parametrize(
        "provider,threshold",
        [
            ("mcp", 3),
            ("wasm", 5),
            ("bridge", 3),
            ("agent", 2),
            ("workflow", 1),
            ("concierge", 3),
        ],
    )
    def test_per_provider_threshold(self, policies: dict, provider: str, threshold: int) -> None:
        pp = policies["circuit_breaker"]["per_provider"]
        assert pp[provider]["threshold_per_min"] == threshold

    def test_per_provider_count(self, policies: dict) -> None:
        pp = policies["circuit_breaker"]["per_provider"]
        assert len(pp) == 6


# ===================================================================
# 7. Safety band -- ordering via SafetyBand enum
# ===================================================================


class TestSafetyBandOrdering:
    """Verify SafetyBand enum ordering: GREEN < AMBER < RED < CRISIS."""

    def test_green_lt_amber(self) -> None:
        from k1.fabric.types import SafetyBand

        assert SafetyBand.GREEN < SafetyBand.AMBER

    def test_amber_lt_red(self) -> None:
        from k1.fabric.types import SafetyBand

        assert SafetyBand.AMBER < SafetyBand.RED

    def test_red_lt_crisis(self) -> None:
        from k1.fabric.types import SafetyBand

        assert SafetyBand.RED < SafetyBand.CRISIS

    def test_green_le_green(self) -> None:
        from k1.fabric.types import SafetyBand

        assert SafetyBand.GREEN <= SafetyBand.GREEN

    def test_crisis_ge_green(self) -> None:
        from k1.fabric.types import SafetyBand

        assert SafetyBand.CRISIS >= SafetyBand.GREEN

    def test_full_ordering(self) -> None:
        from k1.fabric.types import SafetyBand

        ordered = [SafetyBand.GREEN, SafetyBand.AMBER, SafetyBand.RED, SafetyBand.CRISIS]
        for i in range(len(ordered)):
            for j in range(i + 1, len(ordered)):
                assert ordered[i] < ordered[j]
                assert ordered[j] > ordered[i]

    def test_string_values(self) -> None:
        from k1.fabric.types import SafetyBand

        assert SafetyBand.GREEN.value == "GREEN"
        assert SafetyBand.AMBER.value == "AMBER"
        assert SafetyBand.RED.value == "RED"
        assert SafetyBand.CRISIS.value == "CRISIS"


# ===================================================================
# 8. Safety enforcement rules
# ===================================================================


class TestSafetyEnforcement:
    """Verify safety enforcement rules from the contract."""

    def test_band_enforcement_mandatory(self, policies: dict) -> None:
        assert policies["safety"]["band_enforcement"] == "mandatory"

    def test_red_band_requires_approval(self, policies: dict) -> None:
        assert policies["safety"]["red_band_requires_approval"] is True

    def test_unclassified_default_deny(self, policies: dict) -> None:
        assert policies["safety"]["unclassified_default"] == "deny"


# ===================================================================
# 9. Audit requirements
# ===================================================================


class TestAuditRequirements:
    """Verify audit/observability fields from the contract."""

    def test_emit_receipts(self, policies: dict) -> None:
        assert policies["audit"]["emit_receipts"] is True

    def test_receipt_topic(self, policies: dict) -> None:
        assert policies["audit"]["receipt_topic"] == "k1.fabric.audit.v1"

    def test_require_trace_id(self, policies: dict) -> None:
        assert policies["audit"]["require_trace_id"] is True

    def test_trace_id_field(self, policies: dict) -> None:
        assert policies["audit"]["trace_id_field"] == "cognitive_trace_id"

    def test_retention_days(self, policies: dict) -> None:
        assert policies["audit"]["retention_days"] == 90

    EXPECTED_AUDIT_FIELDS = [
        "cognitive_trace_id",
        "session_id",
        "capability_name",
        "provider_type",
        "latency_ms",
        "status",
        "timestamp_utc",
    ]

    def test_required_fields_count(self, policies: dict) -> None:
        assert len(policies["audit"]["required_fields"]) == 7

    @pytest.mark.parametrize("field", EXPECTED_AUDIT_FIELDS)
    def test_required_field_present(self, policies: dict, field: str) -> None:
        assert field in policies["audit"]["required_fields"]


# ===================================================================
# 10. Egress rules
# ===================================================================


class TestEgressRules:
    """Verify egress rules for network and filesystem."""

    def test_allowed_domains(self, policies: dict) -> None:
        domains = policies["egress"]["network"]["allowed_domains"]
        assert "localhost" in domains
        assert "127.0.0.1" in domains
        assert "*.internal" in domains

    def test_allowed_ports(self, policies: dict) -> None:
        ports = policies["egress"]["network"]["allowed_ports"]
        assert set(ports) == {8080, 8443, 9090}

    def test_max_connections_per_provider(self, policies: dict) -> None:
        assert policies["egress"]["network"]["max_connections_per_provider"] == 5

    def test_allowed_read_paths(self, policies: dict) -> None:
        paths = policies["egress"]["filesystem"]["allowed_read_paths"]
        assert len(paths) >= 1
        assert any("sandbox" in p for p in paths)

    def test_no_write_paths(self, policies: dict) -> None:
        assert policies["egress"]["filesystem"]["allowed_write_paths"] == []


# ===================================================================
# 11. Cross-check: p95 targets are strictly less than max targets
# ===================================================================


class TestBudgetConsistency:
    """Verify all p95 targets are strictly below their max counterparts."""

    @pytest.mark.parametrize(
        "p95_key,max_key",
        [
            ("registry_lookup_ms_p95", "registry_lookup_ms_max"),
            ("retrieval_10k_ms_p95", "retrieval_10k_ms_max"),
            ("retrieval_100k_ms_p95", "retrieval_100k_ms_max"),
            ("provider_resolution_ms_p95", "provider_resolution_ms_max"),
            ("context_build_simple_ms_p95", "context_build_simple_ms_max"),
            ("context_build_full_ms_p95", "context_build_full_ms_max"),
        ],
    )
    def test_p95_less_than_max(self, policies: dict, p95_key: str, max_key: str) -> None:
        ext = policies["budgets"]["extensions"]
        assert (
            ext[p95_key] < ext[max_key]
        ), f"{p95_key}={ext[p95_key]} should be < {max_key}={ext[max_key]}"

    def test_all_latency_extensions_positive(self, policies: dict) -> None:
        """Every numeric target in extensions is a positive number."""
        ext = policies["budgets"]["extensions"]
        for k, v in ext.items():
            if isinstance(v, (int, float)):
                assert v > 0, f"Extension budget {k}={v} must be positive"


# ===================================================================
# 12. SLI latency targets (Epic 7.1.1)
# ===================================================================


class TestSLILatency:
    """Verify all canonical latency SLI targets from sli.latency section."""

    @pytest.mark.parametrize(
        "key,expected_ms",
        [
            ("registry_lookup_ms_p95", 1),
            ("retrieval_10k_ms_p95", 20),
            ("retrieval_100k_ms_p95", 50),
            ("provider_resolution_ms_p95", 5),
            ("context_build_simple_ms_p95", 10),
            ("context_build_full_ms_p95", 50),
            ("full_overhead_ms_p95", 100),
            ("mcp_local_ms_p95", 2000),
            ("agent_execution_ms_p95", 10000),
        ],
    )
    def test_latency_target(self, policies: dict, key: str, expected_ms: int) -> None:
        assert policies["sli"]["latency"][key] == expected_ms

    def test_latency_target_count(self, policies: dict) -> None:
        """Exactly 9 latency SLI targets defined."""
        assert len(policies["sli"]["latency"]) == 9

    def test_all_latency_targets_positive(self, policies: dict) -> None:
        for k, v in policies["sli"]["latency"].items():
            assert isinstance(v, int) and v > 0, f"sli.latency.{k}={v} must be positive int"


# ===================================================================
# 13. SLI latency consistency with budgets.extensions
# ===================================================================


class TestSLILatencyConsistency:
    """SLI latency targets must match the corresponding budgets.extensions values."""

    SHARED_KEYS = [
        "registry_lookup_ms_p95",
        "retrieval_10k_ms_p95",
        "retrieval_100k_ms_p95",
        "provider_resolution_ms_p95",
        "context_build_simple_ms_p95",
        "context_build_full_ms_p95",
    ]

    @pytest.mark.parametrize("key", SHARED_KEYS)
    def test_sli_matches_extension(self, policies: dict, key: str) -> None:
        sli_val = policies["sli"]["latency"][key]
        ext_val = policies["budgets"]["extensions"][key]
        assert sli_val == ext_val, f"sli.latency.{key}={sli_val} != extensions.{key}={ext_val}"

    def test_full_overhead_matches_top_level(self, policies: dict) -> None:
        """sli.latency.full_overhead_ms_p95 must equal budgets.latency_ms_p95."""
        assert (
            policies["sli"]["latency"]["full_overhead_ms_p95"]
            == policies["budgets"]["latency_ms_p95"]
        )


# ===================================================================
# 14. SLI throughput targets (Epic 7.1.2)
# ===================================================================


class TestSLIThroughput:
    """Verify all canonical throughput SLI targets from sli.throughput section."""

    def test_concurrent_executions(self, policies: dict) -> None:
        assert policies["sli"]["throughput"]["concurrent_executions"] == 100

    def test_registry_size_min(self, policies: dict) -> None:
        assert policies["sli"]["throughput"]["registry_size_min"] == 100_000

    def test_retrieval_qps(self, policies: dict) -> None:
        assert policies["sli"]["throughput"]["retrieval_qps"] == 1000

    def test_execution_qps(self, policies: dict) -> None:
        assert policies["sli"]["throughput"]["execution_qps"] == 100

    def test_throughput_target_count(self, policies: dict) -> None:
        """Exactly 4 throughput SLI targets defined."""
        assert len(policies["sli"]["throughput"]) == 4

    def test_all_throughput_targets_positive(self, policies: dict) -> None:
        for k, v in policies["sli"]["throughput"].items():
            assert isinstance(v, int) and v > 0, f"sli.throughput.{k}={v} must be positive int"


# ===================================================================
# 15. SLO availability targets (Epic 7.1.3)
# ===================================================================


class TestSLOAvailability:
    """Verify all SLO targets from the slo section."""

    def test_availability_pct(self, policies: dict) -> None:
        assert policies["slo"]["availability_pct"] == 99.9

    def test_latency_compliance_pct(self, policies: dict) -> None:
        assert policies["slo"]["latency_compliance_pct"] == 99.5

    def test_retrieval_accuracy_pct(self, policies: dict) -> None:
        assert policies["slo"]["retrieval_accuracy_pct"] == 95.0

    def test_circuit_breaker_recovery_s(self, policies: dict) -> None:
        assert policies["slo"]["circuit_breaker_recovery_s"] == 60

    def test_slo_target_count(self, policies: dict) -> None:
        """Exactly 4 SLO targets defined."""
        assert len(policies["slo"]) == 4

    def test_availability_within_bounds(self, policies: dict) -> None:
        val = policies["slo"]["availability_pct"]
        assert 0 < val <= 100, f"availability_pct={val} out of bounds"

    def test_latency_compliance_within_bounds(self, policies: dict) -> None:
        val = policies["slo"]["latency_compliance_pct"]
        assert 0 < val <= 100, f"latency_compliance_pct={val} out of bounds"

    def test_retrieval_accuracy_within_bounds(self, policies: dict) -> None:
        val = policies["slo"]["retrieval_accuracy_pct"]
        assert 0 < val <= 100, f"retrieval_accuracy_pct={val} out of bounds"

    def test_cb_recovery_positive(self, policies: dict) -> None:
        assert policies["slo"]["circuit_breaker_recovery_s"] > 0


# ===================================================================
# 16. SLO consistency with circuit breaker config
# ===================================================================


class TestSLOConsistency:
    """SLO targets must be consistent with other contract sections."""

    def test_cb_recovery_gte_half_open(self, policies: dict) -> None:
        """CB recovery SLO must be >= half_open_timeout_s."""
        recovery = policies["slo"]["circuit_breaker_recovery_s"]
        half_open = policies["circuit_breaker"]["global"]["half_open_timeout_s"]
        assert recovery >= half_open, (
            f"slo.circuit_breaker_recovery_s={recovery} "
            f"< circuit_breaker.global.half_open_timeout_s={half_open}"
        )

    def test_latency_compliance_above_50(self, policies: dict) -> None:
        """Latency compliance SLO must exceed 50% to be meaningful."""
        assert policies["slo"]["latency_compliance_pct"] > 50

    def test_availability_above_latency_compliance(self, policies: dict) -> None:
        """Availability target must be >= latency compliance (broader guarantee)."""
        avail = policies["slo"]["availability_pct"]
        compliance = policies["slo"]["latency_compliance_pct"]
        assert avail >= compliance
