# Changelog

<!-- markdownlint-disable MD024 -->

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Removed

#### Automation Cleanup & Microkernel Purity (Milestone A)

- **`k0/automation/remediation_actions.py`** (~2,091 lines)
  - Removed direct kernel remediation logic (privileged `sudo iptables`, `docker-compose`, `kill -9` operations)
  - Remediation is now handled by user-space orchestration layer consuming K0 SSE `infra.remediation.required` events
  - See ADR-0121 for architecture rationale

- **`k0/automation/remediation_service.py`** (~1,847 lines)
  - Removed Flask webhook handler for Alertmanager integration
  - Alert handling now delegated to user-space services consuming K0 SSE events
  - See ADR-0121 for separation-of-concerns rationale

- **`k0/automation/generate_chaos_report.py`** (~412 lines)
  - Removed basic Ward output parser for chaos test reporting
  - Will be superseded by integrated `chaos_scheduler.py` in Milestone E
  - See issue A.1.1 for details

- **`k0/automation/test_service.ps1`** (~187 lines)
  - Removed PowerShell service management script
  - Functionality covered by Ward integration tests
  - See issue A.1.1 for details

- **`k0/automation/test_webhook_payload.json`** (~34 lines)
  - Removed orphaned test fixture
  - Should live in `tests/fixtures/` if needed
  - See issue A.1.1 for details

**Impact**: ~4,571 lines of technical debt removed. Archived to `k0/automation/_archived/deprecated-2025-11-01/` for historical reference.

**Migration Guide**:

- See `docs/architecture/decisions/0121-remediation-service-separation.md` for architecture rationale
- See `docs/development/runbooks/remediation-service.md` for new SSE-based pattern (reference implementation coming in Milestone B)

### Added

- **K1 Temporal / Spatial / Grounding M0 scaffold**
  - Added the long-lived implementation plan at `docs/plans/k1_temporal_spatial_grounding_plan.md`
  - Added inert kernel package and port scaffolding for `k1.temporal`, `k1.spatial`, and `k1.grounding`
  - Added migration feature flags `K1_ENABLE_TEMPORAL`, `K1_ENABLE_SPATIAL`, and `K1_ENABLE_GROUNDING`

- **K1 Temporal M1 E1-E4 service core**
  - Added canonical temporal event contracts, serialization helpers, and internal temporal ports
  - Added clock, timezone, routine, event, metrics, state, and policy adapters for the temporal module
  - Added deterministic anchor, window, freshness, projection, and expression-resolution service modules

- **K0 Automation Enhancement Plan**
  - Comprehensive 6-8 week roadmap for automation infrastructure improvements
  - See `k0/automation/plan.md` for milestones A–G, epics, issues, acceptance criteria
  - Total scope: 13 actionable issues across 7 milestones

---

## [1.0.0-rc1] — 2025-10-15

### Added

- Initial K0 microkernel implementation
- Command, Query, SSE, and Observability ports
- WAL-based ACID transaction semantics
- Schema Registry with N/N+1 compatibility policy
- Contract linting and validation infrastructure

---
