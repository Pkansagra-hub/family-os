"""
k1.fabric.output_validation.structural_validator -- Tier 1: Structural Validation.

Issue 3.5.1 -- StructuralValidator.

Validates the structural integrity of a CapabilityResult before any
schema or semantic checks.  Fast-fail: malformed results are rejected
immediately.

Checks performed (in order):
  1. Required fields present: ``success`` field set, ``data`` xor ``error``
     (success=True -> data is dict, success=False -> error is ErrorInfo).
  2. Data is well-formed: ``data`` is a dict (not a string, not None when
     success=True).
  3. No truncation markers: data values do not contain common truncation
     indicators ("...", "[truncated]", "[output cut]").
  4. Size limits: serialized data size does not exceed ``max_data_bytes``
     (default 1 MiB).

Returns a ``ValidationResult`` with ``tier=STRUCTURAL``.

References:
  - fabric-implementation-plan.md Issue 3.5.1
  - Epic 3.5 wiring: pure structural checks on CapabilityResult (1.3.2)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared validation types (used across all three tiers)
# ---------------------------------------------------------------------------

# Default maximum serialized data size: 1 MiB
DEFAULT_MAX_DATA_BYTES: int = 1_048_576

# Common truncation markers that indicate provider output was cut off
TRUNCATION_MARKERS: tuple[str, ...] = (
    "...",
    "[truncated]",
    "[output cut]",
    "[content truncated]",
    "<!-- truncated -->",
    "[...more]",
)


class ValidationTier(str, Enum):
    """Which validation tier produced the result."""

    STRUCTURAL = "STRUCTURAL"
    SCHEMA = "SCHEMA"
    SEMANTIC = "SEMANTIC"


class ValidationSeverity(str, Enum):
    """How severe the validation failure is."""

    HARD = "HARD"  # Must reject -- structural or schema violation
    SOFT = "SOFT"  # Annotate warning -- semantic concern


@dataclass(frozen=True)
class ValidationIssue:
    """A single validation finding."""

    tier: ValidationTier
    severity: ValidationSeverity
    code: str
    message: str


@dataclass(frozen=True)
class ValidationResult:
    """
    Outcome of one validation tier.

    Attributes:
        valid: True when all checks passed for this tier.
        tier: Which tier produced this result.
        issues: List of findings (empty when valid=True).
        confidence: Confidence score (1.0 for structural/schema, 0..1 for semantic).
        metadata: Optional extra data (e.g. data_size_bytes, truncation_locations).
    """

    valid: bool
    tier: ValidationTier
    issues: List[ValidationIssue] = field(default_factory=list)
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# StructuralValidator configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StructuralValidatorConfig:
    """
    Configuration for StructuralValidator.

    Attributes:
        max_data_bytes: Maximum allowed serialized size of ``result.data``.
        check_truncation: Whether to scan data values for truncation markers.
        max_scan_depth: Maximum recursion depth when scanning for truncation.
    """

    max_data_bytes: int = DEFAULT_MAX_DATA_BYTES
    check_truncation: bool = True
    max_scan_depth: int = 10


# ---------------------------------------------------------------------------
# 3.5.1 -- StructuralValidator
# ---------------------------------------------------------------------------


class StructuralValidator:
    """
    Tier 1 -- structural integrity check on CapabilityResult.

    Stateless.  No external dependencies.  Thread-safe.

    Usage::

        validator = StructuralValidator()
        result = validator.validate(capability_result)
        if not result.valid:
            # reject immediately
    """

    __slots__ = ("_config",)

    def __init__(self, config: Optional[StructuralValidatorConfig] = None) -> None:
        self._config = config or StructuralValidatorConfig()

    # ---- public API --------------------------------------------------------

    def validate(self, result: Any) -> ValidationResult:
        """
        Run all structural checks on *result*.

        Args:
            result: A CapabilityResult (or any object with the expected attrs).

        Returns:
            ValidationResult with tier=STRUCTURAL.
        """
        issues: List[ValidationIssue] = []
        metadata: Dict[str, Any] = {}

        # Check 1: required fields
        self._check_required_fields(result, issues)

        # If required-field check already failed, short-circuit
        if issues:
            return ValidationResult(
                valid=False,
                tier=ValidationTier.STRUCTURAL,
                issues=list(issues),
                metadata=metadata,
            )

        # Check 2: data well-formedness
        self._check_data_wellformed(result, issues)

        # Check 3: truncation markers (only if data exists)
        if (
            self._config.check_truncation
            and getattr(result, "success", False)
            and getattr(result, "data", None) is not None
        ):
            truncation_locations = self._find_truncation_markers(result.data)
            if truncation_locations:
                metadata["truncation_locations"] = truncation_locations
                issues.append(
                    ValidationIssue(
                        tier=ValidationTier.STRUCTURAL,
                        severity=ValidationSeverity.HARD,
                        code="truncation_detected",
                        message=(
                            f"Truncation markers found at: " f"{', '.join(truncation_locations)}"
                        ),
                    )
                )

        # Check 4: size limits (only if data exists)
        if getattr(result, "success", False) and getattr(result, "data", None) is not None:
            data_size = self._measure_data_size(result.data)
            metadata["data_size_bytes"] = data_size
            if data_size > self._config.max_data_bytes:
                issues.append(
                    ValidationIssue(
                        tier=ValidationTier.STRUCTURAL,
                        severity=ValidationSeverity.HARD,
                        code="data_too_large",
                        message=(
                            f"Serialized data size {data_size} bytes exceeds "
                            f"limit of {self._config.max_data_bytes} bytes"
                        ),
                    )
                )

        return ValidationResult(
            valid=len(issues) == 0,
            tier=ValidationTier.STRUCTURAL,
            issues=list(issues),
            metadata=metadata,
        )

    # ---- private checks ----------------------------------------------------

    @staticmethod
    def _check_required_fields(result: Any, issues: List[ValidationIssue]) -> None:
        """Check 1: required fields present with correct invariants."""
        # Must have 'success' attribute
        if not hasattr(result, "success"):
            issues.append(
                ValidationIssue(
                    tier=ValidationTier.STRUCTURAL,
                    severity=ValidationSeverity.HARD,
                    code="missing_success_field",
                    message="Result missing required 'success' field",
                )
            )
            return

        success = result.success

        # success=True requires data, must not have error
        if success:
            if getattr(result, "data", None) is None:
                issues.append(
                    ValidationIssue(
                        tier=ValidationTier.STRUCTURAL,
                        severity=ValidationSeverity.HARD,
                        code="success_without_data",
                        message="success=True but 'data' is None",
                    )
                )
            if getattr(result, "error", None) is not None:
                issues.append(
                    ValidationIssue(
                        tier=ValidationTier.STRUCTURAL,
                        severity=ValidationSeverity.HARD,
                        code="success_with_error",
                        message="success=True but 'error' is set (invariant violation)",
                    )
                )
        else:
            # success=False requires error
            if getattr(result, "error", None) is None:
                issues.append(
                    ValidationIssue(
                        tier=ValidationTier.STRUCTURAL,
                        severity=ValidationSeverity.HARD,
                        code="failure_without_error",
                        message="success=False but 'error' is None",
                    )
                )

    @staticmethod
    def _check_data_wellformed(result: Any, issues: List[ValidationIssue]) -> None:
        """Check 2: data is a dict when success=True."""
        if not getattr(result, "success", False):
            return

        data = getattr(result, "data", None)
        if data is None:
            return  # already caught in check 1

        if not isinstance(data, dict):
            issues.append(
                ValidationIssue(
                    tier=ValidationTier.STRUCTURAL,
                    severity=ValidationSeverity.HARD,
                    code="data_not_dict",
                    message=f"data must be a dict, got {type(data).__name__}",
                )
            )

    def _find_truncation_markers(
        self,
        data: Any,
        path: str = "$",
        depth: int = 0,
    ) -> List[str]:
        """
        Recursively scan data for truncation marker strings.

        Returns list of JSON-path-like locations where markers were found.
        """
        if depth > self._config.max_scan_depth:
            return []

        locations: List[str] = []

        if isinstance(data, str):
            for marker in TRUNCATION_MARKERS:
                if marker in data:
                    locations.append(f"{path} (marker: {marker!r})")
                    break  # one marker per location is enough
        elif isinstance(data, dict):
            for key, value in data.items():
                locations.extend(self._find_truncation_markers(value, f"{path}.{key}", depth + 1))
        elif isinstance(data, (list, tuple)):
            for idx, item in enumerate(data):
                locations.extend(self._find_truncation_markers(item, f"{path}[{idx}]", depth + 1))

        return locations

    @staticmethod
    def _measure_data_size(data: Any) -> int:
        """Measure serialized size of data in bytes (JSON UTF-8)."""
        try:
            return len(json.dumps(data, default=str).encode("utf-8"))
        except (TypeError, ValueError, OverflowError):
            # If serialization fails, treat as oversized
            return DEFAULT_MAX_DATA_BYTES + 1
