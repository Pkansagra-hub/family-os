"""
K0 Automation - Automated Alert Remediation

This package provides automated remediation for common K0 issues.
For a 2-person team, automation reduces toil and enables scale.

Components:
- remediation_service.py: Flask API that receives Alertmanager webhooks
- remediation_actions.py: Concrete remediation implementations

Safety features:
- Throttling (max 3 remediations per alert per hour)
- Dry-run mode for testing
- Manual override to disable automation
- Execution history for compliance
"""

__version__ = "1.0.0"
__author__ = "K0 DevOps Team"
