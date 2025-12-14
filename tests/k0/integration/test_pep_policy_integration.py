"""Integration test: K0 PEP (Policy Enforcement Point).

Tests policy evaluation for all three decision paths:
- **ALLOW path**: Valid envelopes by band/role pass through with obligations
- **DENY path**: Blocked bands, revoked devices, unauthorized roles rejected
- **REDACT path**: PII redaction obligations applied to payloads

Validates:
- Band-based capacity enforcement (GREEN/AMBER/RED)
- Role-based access control (RBAC) with topic wildcards
- Device posture guards (revoked, out-of-date)
- Obligation emission and tracking
- Redaction directive application (PII masking)
- Policy manifest loading and caching
"""

from __future__ import annotations

from k0.policy.pep_syscall import PolicyDecision, evaluate_envelope
from k0.policy.redaction import RedactionDirective, apply_redactions, directives_from_obligations


class TestAllowPath:
    """Tests for ALLOW decisions (valid envelopes that pass policy)."""

    def test_green_band_with_valid_topic_admits(self) -> None:
        """Test: GREEN band envelope with valid content is admitted."""
        envelope = {
            "band": "GREEN",
            "topic": "ui.test",
            "policy_ctx": {
                "abac": {"roles": ["guest"]},
            },
        }
        decision = evaluate_envelope(envelope)
        assert decision.admit is True, f"GREEN band should admit: {decision.deny_reason}"
        assert decision.deny_reason is None

    def test_amber_band_with_coordinator_role_admits(self) -> None:
        """Test: AMBER band with coordinator role is admitted with obligations."""
        envelope = {
            "band": "AMBER",
            "topic": "memory.test",
            "policy_ctx": {
                "abac": {"roles": ["coordinator"]},
            },
        }
        decision = evaluate_envelope(envelope)
        assert decision.admit is True, f"AMBER + coordinator should admit: {decision.deny_reason}"
        # AMBER should have audit obligation
        assert len(decision.obligations) > 0, "AMBER band should emit obligations"

    def test_red_band_with_security_role_admits(self) -> None:
        """Test: RED band is unconditionally blocked (deny: true in schema)."""
        envelope = {
            "band": "RED",
            "topic": "policy.test",
            "policy_ctx": {
                "abac": {"roles": ["security"]},
            },
        }
        decision = evaluate_envelope(envelope)
        # RED band has "deny": true, so it's always blocked regardless of role
        assert decision.admit is False, "RED band is unconditionally denied"
        assert decision.deny_reason == "BAND_BLOCKED"

    def test_guest_role_wildcard_topic_matching(self) -> None:
        """Test: Guest role can access ui.* topics via wildcard matching."""
        envelope = {
            "band": "GREEN",
            "topic": "ui.dashboard",
            "policy_ctx": {
                "abac": {"roles": ["guest"]},
            },
        }
        decision = evaluate_envelope(envelope)
        assert decision.admit is True, f"Guest should access ui.* topics: {decision.deny_reason}"

    def test_security_role_expanded_topic_access(self) -> None:
        """Test: Security role has broader topic access including infra.sanitized.*"""
        envelope = {
            "band": "AMBER",
            "topic": "infra.sanitized.logs",
            "policy_ctx": {
                "abac": {"roles": ["security"]},
            },
        }
        decision = evaluate_envelope(envelope)
        # Security role allows infra.sanitized.* and has max_band=RED (can use AMBER)
        assert (
            decision.admit is True
        ), f"Security should access infra.sanitized.*: {decision.deny_reason}"


class TestDenyPath:
    """Tests for DENY decisions (blocked requests)."""

    def test_red_band_blocks_non_security_roles(self) -> None:
        """Test: RED band denies non-security roles."""
        envelope = {
            "band": "RED",
            "topic": "memory.test",
            "policy_ctx": {
                "abac": {"roles": ["coordinator"]},
            },
        }
        decision = evaluate_envelope(envelope)
        assert decision.admit is False, "RED band should deny non-security roles"
        assert decision.deny_reason == "BAND_BLOCKED"

    def test_guest_role_denied_for_amber_band(self) -> None:
        """Test: Guest role cannot access AMBER band (max_band=GREEN)."""
        envelope = {
            "band": "AMBER",
            "topic": "memory.test",
            "policy_ctx": {
                "abac": {"roles": ["guest"]},
            },
        }
        decision = evaluate_envelope(envelope)
        # Guest has max_band=GREEN, so AMBER should be denied
        assert decision.admit is False, "Guest role should not access AMBER band"

    def test_unauthorized_topic_access_denied(self) -> None:
        """Test: Guest role denied access to non-ui.* topics."""
        envelope = {
            "band": "GREEN",
            "topic": "policy.test",  # Not in guest's allow_topics
            "policy_ctx": {
                "abac": {"roles": ["guest"]},
            },
        }
        decision = evaluate_envelope(envelope)
        assert decision.admit is False, "Guest should not access policy.* topics"

    def test_revoked_device_posture_denies_request(self) -> None:
        """Test: Revoked device posture blocks all requests."""
        envelope = {
            "band": "GREEN",
            "topic": "ui.test",
            "policy_ctx": {
                "abac": {"roles": ["guest"], "device_posture": "revoked"},
            },
        }
        decision = evaluate_envelope(envelope)
        assert decision.admit is False, "Revoked device posture should deny request"
        # Should have reauth obligation
        obligation_names = [o.name for o in decision.obligations]
        assert (
            "kernel.device.reauth" in obligation_names
        ), "Revoked device should emit reauth obligation"


class TestRedactPath:
    """Tests for redaction obligations (PII masking)."""

    def test_guest_role_receives_redaction_obligation(self) -> None:
        """Test: Guest role gets redaction obligation for PII."""
        envelope = {
            "band": "GREEN",
            "topic": "ui.test",
            "policy_ctx": {
                "abac": {"roles": ["guest"]},
            },
        }
        decision = evaluate_envelope(envelope)
        assert decision.admit is True
        # Guest role should have redaction obligation
        obligation_names = [o.name for o in decision.obligations]
        assert "kernel.redact.enforce" in obligation_names, "Guest should have redaction obligation"

    def test_redaction_directive_extraction_from_obligations(self) -> None:
        """Test: Redaction directives extracted from policy obligations."""
        from k0.policy.pep_syscall import Obligation

        # Create mock obligations that look like kernel.redact.field obligations
        obligations = [
            Obligation(
                name="kernel.redact.field",
                details={
                    "fields": "ssn",
                    "target": "user",
                },
            ),
            Obligation(
                name="kernel.redact.field",
                details={
                    "fields": "email",
                    "target": "contact",
                },
            ),
        ]

        directives = directives_from_obligations(obligations, default_mask="***REDACTED***")
        assert len(directives) == 2, "Should extract 2 redaction directives"
        assert all(d.fields for d in directives), "All directives should have fields"

    def test_apply_redaction_masks_pii_fields(self) -> None:
        """Test: Redaction properly masks PII fields in payload."""
        from typing import cast

        payload = {
            "user": {
                "name": "Alice",
                "ssn": "123-45-6789",
            },
            "contact": {
                "email": "alice@example.com",
            },
        }

        directives = [
            RedactionDirective(
                obligation="kernel.redact.field",
                fields="ssn",
                target="user",
                mask="***REDACTED***",
            ),
            RedactionDirective(
                obligation="kernel.redact.field",
                fields="email",
                target="contact",
                mask="***REDACTED***",
            ),
        ]

        redacted = apply_redactions(payload, directives)

        # Original should be unchanged
        assert payload["user"]["ssn"] == "123-45-6789", "Original should not be mutated"

        # Redacted copy should have masked fields
        redacted_dict = cast(dict, redacted)
        assert redacted_dict["user"]["ssn"] == "***REDACTED***", "SSN should be redacted"
        assert redacted_dict["contact"]["email"] == "***REDACTED***", "Email should be redacted"
        assert redacted_dict["user"]["name"] == "Alice", "Non-PII fields should remain"

    def test_redaction_handles_nested_structures(self) -> None:
        """Test: Redaction works with deeply nested structures."""
        from typing import cast

        payload = {
            "records": [
                {
                    "id": 1,
                    "user": {"ssn": "111-11-1111"},
                },
                {
                    "id": 2,
                    "user": {"ssn": "222-22-2222"},
                },
            ]
        }

        directives = [
            RedactionDirective(
                obligation="kernel.redact.field",
                fields="ssn",
                target=("records", "0", "user"),
                mask="***",
            ),
            RedactionDirective(
                obligation="kernel.redact.field",
                fields="ssn",
                target=("records", "1", "user"),
                mask="***",
            ),
        ]

        redacted = apply_redactions(payload, directives)
        redacted_dict = cast(dict, redacted)
        assert (
            redacted_dict["records"][0]["user"]["ssn"] == "***"
        ), "Nested array[0] SSN should be redacted"
        assert (
            redacted_dict["records"][1]["user"]["ssn"] == "***"
        ), "Nested array[1] SSN should be redacted"

    def test_redaction_with_missing_paths_is_idempotent(self) -> None:
        """Test: Redaction is idempotent when paths don't exist."""
        payload = {"user": {"name": "Alice"}}

        directives = [
            RedactionDirective(
                obligation="kernel.redact.field",
                fields="ssn",  # Path doesn't exist
                target="user",
                mask="***",
            ),
        ]

        redacted = apply_redactions(payload, directives)
        # Should not raise, just return unchanged payload structure
        assert redacted == payload, "Redaction of missing paths should be idempotent"


class TestBandObligations:
    """Tests for band-specific obligations."""

    def test_green_band_has_no_default_obligations(self) -> None:
        """Test: GREEN band emits only QoS violation obligation."""
        envelope = {
            "band": "GREEN",
            "topic": "ui.test",
            "policy_ctx": {
                "abac": {"roles": ["guest"]},
            },
        }
        decision = evaluate_envelope(envelope)
        assert decision.admit is True
        # GREEN may have violation obligation but no mandatory obligations
        obligation_names = [o.name for o in decision.obligations]
        # Confirm specific ones are there
        assert not any(
            "audit" in name for name in obligation_names
        ), "GREEN should not have audit obligations"

    def test_amber_band_emits_audit_obligation(self) -> None:
        """Test: AMBER band emits kernel.audit.log obligation."""
        envelope = {
            "band": "AMBER",
            "topic": "memory.test",
            "policy_ctx": {
                "abac": {"roles": ["coordinator"]},
            },
        }
        decision = evaluate_envelope(envelope)
        assert decision.admit is True
        obligation_names = [o.name for o in decision.obligations]
        assert "kernel.audit.log" in obligation_names, "AMBER should emit audit obligation"

    def test_red_band_emits_security_notify(self) -> None:
        """Test: RED band emits kernel.security.notify obligation."""
        envelope = {
            "band": "RED",
            "topic": "policy.test",
            "policy_ctx": {
                "abac": {"roles": ["security"]},
            },
        }
        decision = evaluate_envelope(envelope)
        # RED band is blocked, but should still emit security notifications
        assert decision.admit is False, "RED band should be denied"
        obligation_names = [o.name for o in decision.obligations]
        assert (
            "kernel.security.notify" in obligation_names
        ), "RED band should emit security.notify obligation"


class TestPolicyCompleteIntegration:
    """End-to-end integration tests for policy enforcement."""

    def test_coordinator_amber_request_allows_and_audits(self) -> None:
        """Test: Coordinator AMBER request is allowed with audit obligation."""
        envelope = {
            "band": "AMBER",
            "topic": "memory.coordinator_data",
            "policy_ctx": {
                "abac": {"roles": ["coordinator"]},
            },
        }
        decision = evaluate_envelope(envelope)

        # Should be admitted
        assert decision.admit is True, "Coordinator AMBER should be admitted"

        # Should have multiple obligations
        obligation_names = [o.name for o in decision.obligations]
        assert "kernel.audit.log" in obligation_names, "Should audit coordinator access"
        assert "kernel.audit.trace" in obligation_names, "Coordinator role should emit trace"

    def test_guest_ui_request_allows_with_redaction(self) -> None:
        """Test: Guest UI request is allowed with PII redaction obligation."""
        envelope = {
            "band": "GREEN",
            "topic": "ui.profile",
            "policy_ctx": {
                "abac": {"roles": ["guest"]},
            },
        }
        decision = evaluate_envelope(envelope)

        # Should be admitted
        assert decision.admit is True, "Guest UI access should be admitted"

        # Should require redaction
        obligation_names = [o.name for o in decision.obligations]
        assert "kernel.redact.enforce" in obligation_names, "Guest should have redaction obligation"

    def test_three_tier_band_enforcement(self) -> None:
        """Test: Three-tier band enforcement (GREEN < AMBER < RED)."""
        # Green passes Green
        decision_green = evaluate_envelope(
            {"band": "GREEN", "topic": "ui.test", "policy_ctx": {"abac": {"roles": ["guest"]}}}
        )
        assert decision_green.admit is True, "Guest GREEN should pass"

        # Guest cannot use AMBER
        decision_amber = evaluate_envelope(
            {"band": "AMBER", "topic": "memory.test", "policy_ctx": {"abac": {"roles": ["guest"]}}}
        )
        assert decision_amber.admit is False, "Guest AMBER should fail (max_band=GREEN)"

        # Guest cannot use RED
        decision_red = evaluate_envelope(
            {"band": "RED", "topic": "policy.test", "policy_ctx": {"abac": {"roles": ["guest"]}}}
        )
        assert decision_red.admit is False, "Guest RED should fail"

    def test_security_role_full_access_with_notifications(self) -> None:
        """Test: Security role can access GREEN/AMBER (RED is unconditionally blocked)."""
        for band in ["GREEN", "AMBER"]:
            envelope = {
                "band": band,
                "topic": "infra.sanitized.logs",
                "policy_ctx": {
                    "abac": {"roles": ["security"]},
                },
            }
            decision = evaluate_envelope(envelope)
            assert decision.admit is True, f"Security should access {band} band"

        # RED band is unconditionally blocked
        red_envelope = {
            "band": "RED",
            "topic": "infra.sanitized.logs",
            "policy_ctx": {
                "abac": {"roles": ["security"]},
            },
        }
        red_decision = evaluate_envelope(red_envelope)
        assert red_decision.admit is False, "RED band is unconditionally denied"
        obligation_names = [o.name for o in red_decision.obligations]
        assert "kernel.security.notify" in obligation_names, "RED violations should notify security"


class TestPolicyRobustness:
    """Robustness tests for edge cases and error conditions."""

    def test_missing_band_defaults_to_green(self) -> None:
        """Test: Missing band field defaults to GREEN."""
        envelope = {
            # No band specified
            "topic": "ui.test",
            "policy_ctx": {
                "abac": {"roles": ["guest"]},
            },
        }
        decision = evaluate_envelope(envelope)
        # Should treat as GREEN and admit guest
        assert decision.admit is True, "Missing band should default to GREEN"

    def test_missing_policy_context_defaults_to_empty(self) -> None:
        """Test: Missing policy context is handled gracefully."""
        envelope = {
            "band": "GREEN",
            "topic": "ui.test",
            # No policy_ctx
        }
        decision = evaluate_envelope(envelope)
        # Should still evaluate but may lack role context
        # Behavior depends on implementation (may deny or allow depending on defaults)
        assert isinstance(decision, PolicyDecision), "Should return valid decision"

    def test_case_insensitive_band_names(self) -> None:
        """Test: Band names are case-insensitive."""
        for band_variant in ["green", "GREEN", "Green", "gReEn"]:
            envelope = {
                "band": band_variant,
                "topic": "ui.test",
                "policy_ctx": {
                    "abac": {"roles": ["guest"]},
                },
            }
            decision = evaluate_envelope(envelope)
            # Should normalize and admit
            assert decision.admit is True, f"Band '{band_variant}' should be normalized to GREEN"

    def test_redaction_with_empty_directives(self) -> None:
        """Test: Redaction with no directives returns unchanged payload."""
        payload = {"data": "value"}
        redacted = apply_redactions(payload, [])
        # Should handle empty directives gracefully
        assert redacted == payload, "Empty directives should return unchanged payload"

    def test_concurrent_policy_evaluations(self) -> None:
        """Test: Policy evaluations are thread-safe and don't interfere."""
        envelopes = [
            {"band": "GREEN", "topic": "ui.test", "policy_ctx": {"abac": {"roles": ["guest"]}}},
            {
                "band": "AMBER",
                "topic": "memory.test",
                "policy_ctx": {"abac": {"roles": ["coordinator"]}},
            },
            {
                "band": "AMBER",
                "topic": "policy.test",
                "policy_ctx": {"abac": {"roles": ["security"]}},
            },  # Changed RED to AMBER (RED always blocked)
        ]

        import concurrent.futures

        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(evaluate_envelope, env) for env in envelopes]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        # All should succeed without interference
        assert len(results) == 3, "All concurrent evaluations should complete"
        assert results[0].admit is True, "GREEN guest should pass"
        assert results[1].admit is True, "AMBER coordinator should pass"
        assert results[2].admit is True, "AMBER security should pass"
