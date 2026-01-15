"""Tests for simple audit trail."""

from __future__ import annotations

from k0.pipelines.p03.security.audit_trail import (
    AuditAction,
    AuditEntry,
    P03AuditTrail,
    get_audit_trail,
    log_audit,
)


class TestAuditAction:
    """Tests for AuditAction enum."""

    def test_actions_exist(self) -> None:
        """Verify expected actions exist."""
        assert AuditAction.CONSOLIDATE.value == "CONSOLIDATE"
        assert AuditAction.LINK.value == "LINK"
        assert AuditAction.PRUNE.value == "PRUNE"
        assert AuditAction.RESURRECT.value == "RESURRECT"


class TestAuditEntry:
    """Tests for AuditEntry dataclass."""

    def test_create_entry(self) -> None:
        """Create audit entry."""
        entry = AuditEntry(
            action=AuditAction.CONSOLIDATE,
            entity_id="ent-1",
            details={"confidence": 0.95},
        )
        assert entry.action == AuditAction.CONSOLIDATE
        assert entry.entity_id == "ent-1"
        assert entry.details["confidence"] == 0.95
        assert entry.timestamp_ms > 0

    def test_to_dict(self) -> None:
        """Convert entry to dict."""
        entry = AuditEntry(
            action=AuditAction.PRUNE,
            entity_id="ent-2",
            details={"reason": "decay"},
        )
        d = entry.to_dict()
        assert d["action"] == "PRUNE"
        assert d["entity_id"] == "ent-2"


class TestP03AuditTrail:
    """Tests for P03AuditTrail."""

    def test_log_entry(self) -> None:
        """Log an entry."""
        trail = P03AuditTrail()
        trail.log(AuditAction.CONSOLIDATE, "ent-1", confidence=0.9)
        assert trail.count == 1

    def test_get_recent(self) -> None:
        """Get recent entries."""
        trail = P03AuditTrail()
        trail.log(AuditAction.CONSOLIDATE, "ent-1")
        trail.log(AuditAction.LINK, "ent-2")
        trail.log(AuditAction.PRUNE, "ent-3")

        recent = trail.get_recent(2)
        assert len(recent) == 2
        assert recent[-1].action == AuditAction.PRUNE

    def test_get_for_entity(self) -> None:
        """Get entries for specific entity."""
        trail = P03AuditTrail()
        trail.log(AuditAction.CONSOLIDATE, "ent-1")
        trail.log(AuditAction.LINK, "ent-1")
        trail.log(AuditAction.PRUNE, "ent-2")

        entries = trail.get_for_entity("ent-1")
        assert len(entries) == 2

    def test_max_entries_bounded(self) -> None:
        """Trail respects max entries."""
        trail = P03AuditTrail(max_entries=5)
        for i in range(10):
            trail.log(AuditAction.CONSOLIDATE, f"ent-{i}")
        assert trail.count == 5

    def test_log_consolidation(self) -> None:
        """Convenience method for consolidation."""
        trail = P03AuditTrail()
        trail.log_consolidation(
            entity_id="ent-1",
            source_events=["evt-1", "evt-2"],
            formula="weighted_sum",
            confidence=0.95,
        )
        entries = trail.get_for_entity("ent-1")
        assert len(entries) == 1
        assert entries[0].details["formula"] == "weighted_sum"

    def test_log_prune(self) -> None:
        """Convenience method for pruning."""
        trail = P03AuditTrail()
        trail.log_prune(
            entity_id="ent-1",
            reason="decay",
            decay_factor=0.01,
        )
        entries = trail.get_for_entity("ent-1")
        assert entries[0].details["decay_factor"] == 0.01

    def test_explain_decision(self) -> None:
        """Generate explanation for entity."""
        trail = P03AuditTrail()
        trail.log(AuditAction.CONSOLIDATE, "ent-1", source="evt-1")
        trail.log(AuditAction.PRUNE, "ent-1", reason="decay")

        explanation = trail.explain_decision("ent-1")
        assert "ent-1" in explanation
        assert "CONSOLIDATE" in explanation
        assert "PRUNE" in explanation

    def test_clear(self) -> None:
        """Clear trail."""
        trail = P03AuditTrail()
        trail.log(AuditAction.CONSOLIDATE, "ent-1")
        assert trail.count == 1
        trail.clear()
        assert trail.count == 0


class TestGlobalAuditTrail:
    """Tests for global audit trail functions."""

    def test_get_audit_trail_singleton(self) -> None:
        """get_audit_trail returns same instance."""
        trail1 = get_audit_trail()
        trail2 = get_audit_trail()
        assert trail1 is trail2

    def test_log_audit_convenience(self) -> None:
        """log_audit convenience function works."""
        trail = get_audit_trail()
        initial_count = trail.count
        log_audit(AuditAction.FEEDBACK, "ent-test", rating=5)
        assert trail.count == initial_count + 1
