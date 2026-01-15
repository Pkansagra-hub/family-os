"""Security module for P03 pipeline.

Provides privacy band enforcement, retention, fingerprinting,
and simple audit/tombstone management for device deployment.

Device-focused (not multi-tenant SaaS):
- PrivacyBandEnforcer: Controls external sharing
- DeviceRetentionPolicy: Storage management
- ContentFingerprint: Deduplication
- P03AuditTrail: Debug logging
- Tombstone: Soft-delete for undo

Related Issues: 6.3.10, 6.3.11, 6.3.13, 6.3.15, 6.3.16, 6.3.17
"""

from k0.pipelines.p03.security.audit_trail import (
    AuditAction,
    AuditEntry,
    P03AuditTrail,
    get_audit_trail,
    log_audit,
)
from k0.pipelines.p03.security.device_retention import (
    RETENTION_DAYS,
    DeviceRetentionPolicy,
    RetentionAction,
    RetentionDecision,
    run_retention_cleanup,
)
from k0.pipelines.p03.security.fingerprint import (
    ContentFingerprint,
    DuplicateDetector,
    deduplicate_events,
    fingerprint_event,
    fingerprint_memory,
    fingerprint_structured,
    fingerprint_text,
)
from k0.pipelines.p03.security.location_masking import (
    MaskedLocation,
    get_safe_location_description,
    mask_for_external_api,
    should_include_location,
)
from k0.pipelines.p03.security.privacy_band import (
    BAND_CONSTRAINTS,
    BandConstraints,
    PrivacyBand,
    PrivacyBandEnforcer,
)
from k0.pipelines.p03.security.query_auditor import (
    CrossSpaceAuditor,
    QueryViolation,
    SecurityReport,
    run_security_scan,
)
from k0.pipelines.p03.security.rls_verifier import (
    RLS_REQUIRED_TABLES,
    PolicyInfo,
    RLSHealthReport,
    check_rls_health,
    emit_rls_health_metric,
    get_required_tables,
    verify_on_startup,
    verify_rls_enabled,
    verify_rls_policies,
)
from k0.pipelines.p03.security.tombstone import (
    TOMBSTONE_RETENTION_DAYS,
    TombstoneInfo,
    TombstoneState,
    can_restore,
    cleanup_expired_tombstones,
    get_tombstoned_items,
    restore,
    soft_delete,
)

__all__ = [
    # Privacy Band Enforcer (6.3.10)
    "BAND_CONSTRAINTS",
    "BandConstraints",
    "PrivacyBand",
    "PrivacyBandEnforcer",
    # Location Masking (6.3.11)
    "MaskedLocation",
    "get_safe_location_description",
    "mask_for_external_api",
    "should_include_location",
    # Audit Trail (6.3.13)
    "AuditAction",
    "AuditEntry",
    "P03AuditTrail",
    "get_audit_trail",
    "log_audit",
    # Tombstone (6.3.15)
    "TOMBSTONE_RETENTION_DAYS",
    "TombstoneInfo",
    "TombstoneState",
    "can_restore",
    "cleanup_expired_tombstones",
    "get_tombstoned_items",
    "restore",
    "soft_delete",
    # Device Retention (6.3.16)
    "RETENTION_DAYS",
    "DeviceRetentionPolicy",
    "RetentionAction",
    "RetentionDecision",
    "run_retention_cleanup",
    # Fingerprint (6.3.17)
    "ContentFingerprint",
    "DuplicateDetector",
    "deduplicate_events",
    "fingerprint_event",
    "fingerprint_memory",
    "fingerprint_structured",
    "fingerprint_text",
    # Query Auditor (legacy, kept for compatibility)
    "CrossSpaceAuditor",
    "QueryViolation",
    "SecurityReport",
    "run_security_scan",
    # RLS Verifier (legacy, kept for compatibility)
    "PolicyInfo",
    "RLS_REQUIRED_TABLES",
    "RLSHealthReport",
    "check_rls_health",
    "emit_rls_health_metric",
    "get_required_tables",
    "verify_on_startup",
    "verify_rls_enabled",
    "verify_rls_policies",
]
