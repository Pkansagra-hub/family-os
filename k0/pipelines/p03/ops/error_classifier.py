"""P03 Error Classification — Issue 6.2.1.

Classifies exceptions into TRANSIENT, VALIDATION, LOGIC, or FATAL categories
for routing to retry scheduler, DLQ, or circuit breaker.

References:
- Dossier Section 13.2: Error Classification
- M6_EXECUTION.md Issue 6.2.1
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, FrozenSet, Type

if TYPE_CHECKING:
    pass

# Import P03ErrorType from runner_contract
from k0.pipelines.p03.runner_contract import P03ErrorType


class P03ErrorCategory(Enum):
    """Error categories for routing decisions.

    TRANSIENT: Retry via RetryScheduler (connection issues, timeouts)
    VALIDATION: DLQ, no retry (schema errors, constraint violations)
    LOGIC: DLQ + alert (reconciliation failures, data integrity)
    FATAL: Circuit breaker, abort cycle (OOM, disk full)
    """

    TRANSIENT = "TRANSIENT"
    VALIDATION = "VALIDATION"
    LOGIC = "LOGIC"
    FATAL = "FATAL"


# =============================================================================
# EXCEPTION TYPE SETS
# =============================================================================

# Transient exceptions (retriable with backoff)
TRANSIENT_EXCEPTIONS: FrozenSet[Type[BaseException]] = frozenset(
    {
        ConnectionError,
        TimeoutError,
        ConnectionRefusedError,
        ConnectionResetError,
        BrokenPipeError,
        BlockingIOError,
    }
)

# Validation exceptions (DLQ, no retry)
VALIDATION_EXCEPTIONS: FrozenSet[Type[BaseException]] = frozenset(
    {
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
    }
)

# Fatal exceptions (abort cycle, circuit breaker)
FATAL_EXCEPTIONS: FrozenSet[Type[BaseException]] = frozenset(
    {
        MemoryError,
        SystemExit,
        KeyboardInterrupt,
        RecursionError,
    }
)


# =============================================================================
# ASYNCPG EXCEPTION CLASSIFICATION
# =============================================================================

# Exception class names for asyncpg (checked by name to avoid import dependency)
ASYNCPG_TRANSIENT_NAMES: FrozenSet[str] = frozenset(
    {
        "PostgresConnectionError",
        "InterfaceError",
        "TooManyConnectionsError",
        "ConnectionDoesNotExistError",
        "CannotConnectNowError",
    }
)

ASYNCPG_VALIDATION_NAMES: FrozenSet[str] = frozenset(
    {
        "DataError",
        "IntegrityConstraintViolationError",
        "CheckViolationError",
        "NotNullViolationError",
        "ForeignKeyViolationError",
        "UniqueViolationError",
        "ExclusionViolationError",
    }
)

ASYNCPG_FATAL_NAMES: FrozenSet[str] = frozenset(
    {
        "InternalServerError",
        "OutOfMemoryError",
        "DiskFullError",
    }
)


# =============================================================================
# P03ERRORTYPE → P03ERRORCATEGORY MAPPING
# =============================================================================

ERROR_TYPE_MAPPING: dict[P03ErrorType, P03ErrorCategory] = {
    # Transient errors (retriable)
    P03ErrorType.DB_TIMEOUT: P03ErrorCategory.TRANSIENT,
    P03ErrorType.LOCK_TIMEOUT: P03ErrorCategory.TRANSIENT,
    P03ErrorType.POOL_EXHAUSTED: P03ErrorCategory.TRANSIENT,
    P03ErrorType.R6_VERSION_CONFLICT: P03ErrorCategory.TRANSIENT,
    P03ErrorType.R7_VERSION_CONFLICT: P03ErrorCategory.TRANSIENT,
    # Validation errors (DLQ, no retry)
    P03ErrorType.R6_UNIQUE_VIOLATION: P03ErrorCategory.VALIDATION,
    P03ErrorType.R6_MANIFEST_INVALID: P03ErrorCategory.VALIDATION,
    # Logic errors (DLQ + alert)
    P03ErrorType.R7_TRANSACTION_FAILED: P03ErrorCategory.LOGIC,
    P03ErrorType.GENERIC: P03ErrorCategory.LOGIC,
}


class ErrorClassifier:
    """Classify exceptions for routing to retry, DLQ, or abort.

    Classification order:
    1. Check for typed P03 errors (P03ErrorType attribute)
    2. Check exception type hierarchy (FATAL → TRANSIENT → VALIDATION)
    3. Check asyncpg exception names
    4. Default to LOGIC (DLQ + alert)
    """

    def classify(self, error: BaseException) -> P03ErrorCategory:
        """Classify exception into routing category.

        Args:
            error: The exception to classify.

        Returns:
            P03ErrorCategory for routing decision.
        """
        # 1. Check typed P03 errors first
        if hasattr(error, "error_type"):
            error_type = getattr(error, "error_type")
            if isinstance(error_type, P03ErrorType):
                return ERROR_TYPE_MAPPING.get(error_type, P03ErrorCategory.LOGIC)

        # 2. Check exception type hierarchy
        for exc_type in FATAL_EXCEPTIONS:
            if isinstance(error, exc_type):
                return P03ErrorCategory.FATAL

        for exc_type in TRANSIENT_EXCEPTIONS:
            if isinstance(error, exc_type):
                return P03ErrorCategory.TRANSIENT

        for exc_type in VALIDATION_EXCEPTIONS:
            if isinstance(error, exc_type):
                return P03ErrorCategory.VALIDATION

        # 3. Check asyncpg exceptions by class name
        exc_name = type(error).__name__
        if exc_name in ASYNCPG_FATAL_NAMES:
            return P03ErrorCategory.FATAL
        if exc_name in ASYNCPG_TRANSIENT_NAMES:
            return P03ErrorCategory.TRANSIENT
        if exc_name in ASYNCPG_VALIDATION_NAMES:
            return P03ErrorCategory.VALIDATION

        # 4. Check for OSError with disk/space issues
        if isinstance(error, OSError):
            err_str = str(error).lower()
            if "disk full" in err_str or "no space" in err_str:
                return P03ErrorCategory.FATAL
            # Other OSError → transient (network, file system)
            return P03ErrorCategory.TRANSIENT

        # 5. Default to LOGIC (DLQ + alert)
        return P03ErrorCategory.LOGIC

    def is_retriable(self, error: BaseException) -> bool:
        """Check if error should be retried.

        Args:
            error: The exception to check.

        Returns:
            True if error is TRANSIENT and should be retried.
        """
        return self.classify(error) == P03ErrorCategory.TRANSIENT

    def is_fatal(self, error: BaseException) -> bool:
        """Check if error is fatal and should abort cycle.

        Args:
            error: The exception to check.

        Returns:
            True if error is FATAL.
        """
        return self.classify(error) == P03ErrorCategory.FATAL

    def should_alert(self, error: BaseException) -> bool:
        """Check if error should trigger an alert.

        Args:
            error: The exception to check.

        Returns:
            True if error is LOGIC or FATAL.
        """
        category = self.classify(error)
        return category in (P03ErrorCategory.LOGIC, P03ErrorCategory.FATAL)
