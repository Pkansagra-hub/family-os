"""E7.M1.2 — KernelConfig HIL field defaults & overrides."""

from __future__ import annotations

from k1.concierge.config.kernel import KernelConfig


class TestKernelConfigHILDefaults:
    """Defaults must match HILConfig defaults so kernel construction is a
    one-for-one mapping."""

    def test_enable_hil_service_default_true(self) -> None:
        assert KernelConfig().enable_hil_service is True

    def test_clarification_rounds_default(self) -> None:
        assert KernelConfig().hil_max_clarification_rounds == 2

    def test_clarification_timeout_default(self) -> None:
        assert KernelConfig().hil_clarification_timeout_ms == 60_000

    def test_approval_timeout_default(self) -> None:
        assert KernelConfig().hil_approval_timeout_ms == 120_000

    def test_needs_human_timeout_default(self) -> None:
        assert KernelConfig().hil_needs_human_timeout_ms == 60_000

    def test_override_timeout_default(self) -> None:
        assert KernelConfig().hil_override_timeout_ms == 60_000

    def test_capability_gate_timeout_default(self) -> None:
        assert KernelConfig().hil_capability_gate_timeout_ms == 120_000

    def test_audit_topic_enabled_by_default(self) -> None:
        assert KernelConfig().hil_enable_audit_topic is True

    def test_llm_synthesis_enabled_by_default(self) -> None:
        assert KernelConfig().hil_enable_llm_synthesis is True


class TestKernelConfigHILOverrides:
    """Explicit overrides flow through unchanged."""

    def test_disable_hil_service(self) -> None:
        cfg = KernelConfig(enable_hil_service=False)
        assert cfg.enable_hil_service is False

    def test_custom_timeouts(self) -> None:
        cfg = KernelConfig(
            hil_clarification_timeout_ms=10_000,
            hil_approval_timeout_ms=20_000,
            hil_max_clarification_rounds=5,
        )
        assert cfg.hil_clarification_timeout_ms == 10_000
        assert cfg.hil_approval_timeout_ms == 20_000
        assert cfg.hil_max_clarification_rounds == 5

    def test_disable_audit_and_llm(self) -> None:
        cfg = KernelConfig(
            hil_enable_audit_topic=False,
            hil_enable_llm_synthesis=False,
        )
        assert cfg.hil_enable_audit_topic is False
        assert cfg.hil_enable_llm_synthesis is False
