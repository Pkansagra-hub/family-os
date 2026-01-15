"""Tests for P03 Error Classifier (Issue 6.2.1).

Tests error classification logic for routing to retry, DLQ, or abort.
"""

from __future__ import annotations

import pytest

from k0.pipelines.p03.ops.error_classifier import (
    ASYNCPG_FATAL_NAMES,
    ASYNCPG_TRANSIENT_NAMES,
    ASYNCPG_VALIDATION_NAMES,
    ERROR_TYPE_MAPPING,
    FATAL_EXCEPTIONS,
    TRANSIENT_EXCEPTIONS,
    VALIDATION_EXCEPTIONS,
    ErrorClassifier,
    P03ErrorCategory,
)
from k0.pipelines.p03.runner_contract import P03ErrorType


class TestP03ErrorCategory:
    """Tests for P03ErrorCategory enum."""

    def test_has_transient(self) -> None:
        """Test TRANSIENT category exists."""
        assert P03ErrorCategory.TRANSIENT.value == "TRANSIENT"

    def test_has_validation(self) -> None:
        """Test VALIDATION category exists."""
        assert P03ErrorCategory.VALIDATION.value == "VALIDATION"

    def test_has_logic(self) -> None:
        """Test LOGIC category exists."""
        assert P03ErrorCategory.LOGIC.value == "LOGIC"

    def test_has_fatal(self) -> None:
        """Test FATAL category exists."""
        assert P03ErrorCategory.FATAL.value == "FATAL"


class TestExceptionSets:
    """Tests for exception type sets."""

    def test_transient_exceptions_not_empty(self) -> None:
        """Test TRANSIENT_EXCEPTIONS is populated."""
        assert len(TRANSIENT_EXCEPTIONS) > 0
        assert ConnectionError in TRANSIENT_EXCEPTIONS
        assert TimeoutError in TRANSIENT_EXCEPTIONS

    def test_validation_exceptions_not_empty(self) -> None:
        """Test VALIDATION_EXCEPTIONS is populated."""
        assert len(VALIDATION_EXCEPTIONS) > 0
        assert ValueError in VALIDATION_EXCEPTIONS
        assert TypeError in VALIDATION_EXCEPTIONS

    def test_fatal_exceptions_not_empty(self) -> None:
        """Test FATAL_EXCEPTIONS is populated."""
        assert len(FATAL_EXCEPTIONS) > 0
        assert MemoryError in FATAL_EXCEPTIONS
        assert SystemExit in FATAL_EXCEPTIONS


class TestAsyncpgExceptionNames:
    """Tests for asyncpg exception name sets."""

    def test_asyncpg_transient_names(self) -> None:
        """Test asyncpg transient exception names."""
        assert "PostgresConnectionError" in ASYNCPG_TRANSIENT_NAMES
        assert "TooManyConnectionsError" in ASYNCPG_TRANSIENT_NAMES

    def test_asyncpg_validation_names(self) -> None:
        """Test asyncpg validation exception names."""
        assert "UniqueViolationError" in ASYNCPG_VALIDATION_NAMES
        assert "IntegrityConstraintViolationError" in ASYNCPG_VALIDATION_NAMES

    def test_asyncpg_fatal_names(self) -> None:
        """Test asyncpg fatal exception names."""
        assert "InternalServerError" in ASYNCPG_FATAL_NAMES
        assert "OutOfMemoryError" in ASYNCPG_FATAL_NAMES


class TestErrorTypeMapping:
    """Tests for P03ErrorType → P03ErrorCategory mapping."""

    def test_db_timeout_is_transient(self) -> None:
        """Test DB_TIMEOUT maps to TRANSIENT."""
        assert ERROR_TYPE_MAPPING[P03ErrorType.DB_TIMEOUT] == P03ErrorCategory.TRANSIENT

    def test_lock_timeout_is_transient(self) -> None:
        """Test LOCK_TIMEOUT maps to TRANSIENT."""
        assert ERROR_TYPE_MAPPING[P03ErrorType.LOCK_TIMEOUT] == P03ErrorCategory.TRANSIENT

    def test_version_conflict_is_transient(self) -> None:
        """Test version conflicts map to TRANSIENT."""
        assert ERROR_TYPE_MAPPING[P03ErrorType.R6_VERSION_CONFLICT] == P03ErrorCategory.TRANSIENT
        assert ERROR_TYPE_MAPPING[P03ErrorType.R7_VERSION_CONFLICT] == P03ErrorCategory.TRANSIENT

    def test_unique_violation_is_validation(self) -> None:
        """Test R6_UNIQUE_VIOLATION maps to VALIDATION."""
        assert ERROR_TYPE_MAPPING[P03ErrorType.R6_UNIQUE_VIOLATION] == P03ErrorCategory.VALIDATION

    def test_manifest_invalid_is_validation(self) -> None:
        """Test R6_MANIFEST_INVALID maps to VALIDATION."""
        assert ERROR_TYPE_MAPPING[P03ErrorType.R6_MANIFEST_INVALID] == P03ErrorCategory.VALIDATION

    def test_transaction_failed_is_logic(self) -> None:
        """Test R7_TRANSACTION_FAILED maps to LOGIC."""
        assert ERROR_TYPE_MAPPING[P03ErrorType.R7_TRANSACTION_FAILED] == P03ErrorCategory.LOGIC

    def test_generic_is_logic(self) -> None:
        """Test GENERIC maps to LOGIC."""
        assert ERROR_TYPE_MAPPING[P03ErrorType.GENERIC] == P03ErrorCategory.LOGIC


class TestErrorClassifier:
    """Tests for ErrorClassifier class."""

    @pytest.fixture
    def classifier(self) -> ErrorClassifier:
        """Create ErrorClassifier instance."""
        return ErrorClassifier()

    def test_classify_connection_error(self, classifier: ErrorClassifier) -> None:
        """Test ConnectionError classified as TRANSIENT."""
        error = ConnectionError("Connection refused")
        assert classifier.classify(error) == P03ErrorCategory.TRANSIENT

    def test_classify_timeout_error(self, classifier: ErrorClassifier) -> None:
        """Test TimeoutError classified as TRANSIENT."""
        error = TimeoutError("Operation timed out")
        assert classifier.classify(error) == P03ErrorCategory.TRANSIENT

    def test_classify_value_error(self, classifier: ErrorClassifier) -> None:
        """Test ValueError classified as VALIDATION."""
        error = ValueError("Invalid value")
        assert classifier.classify(error) == P03ErrorCategory.VALIDATION

    def test_classify_type_error(self, classifier: ErrorClassifier) -> None:
        """Test TypeError classified as VALIDATION."""
        error = TypeError("Wrong type")
        assert classifier.classify(error) == P03ErrorCategory.VALIDATION

    def test_classify_memory_error(self, classifier: ErrorClassifier) -> None:
        """Test MemoryError classified as FATAL."""
        error = MemoryError("Out of memory")
        assert classifier.classify(error) == P03ErrorCategory.FATAL

    def test_classify_unknown_error(self, classifier: ErrorClassifier) -> None:
        """Test unknown exception classified as LOGIC."""
        error = Exception("Unknown error")
        assert classifier.classify(error) == P03ErrorCategory.LOGIC

    def test_classify_runtime_error(self, classifier: ErrorClassifier) -> None:
        """Test RuntimeError classified as LOGIC."""
        error = RuntimeError("Runtime issue")
        assert classifier.classify(error) == P03ErrorCategory.LOGIC


class TestErrorClassifierWithTypedErrors:
    """Tests for ErrorClassifier with P03ErrorType attribute."""

    @pytest.fixture
    def classifier(self) -> ErrorClassifier:
        """Create ErrorClassifier instance."""
        return ErrorClassifier()

    def test_classify_typed_db_timeout(self, classifier: ErrorClassifier) -> None:
        """Test typed error with DB_TIMEOUT."""

        class TypedError(Exception):
            def __init__(self) -> None:
                super().__init__("DB timeout")
                self.error_type = P03ErrorType.DB_TIMEOUT

        error = TypedError()
        assert classifier.classify(error) == P03ErrorCategory.TRANSIENT

    def test_classify_typed_version_conflict(self, classifier: ErrorClassifier) -> None:
        """Test typed error with R6_VERSION_CONFLICT."""

        class TypedError(Exception):
            def __init__(self) -> None:
                super().__init__("Version conflict")
                self.error_type = P03ErrorType.R6_VERSION_CONFLICT

        error = TypedError()
        assert classifier.classify(error) == P03ErrorCategory.TRANSIENT

    def test_classify_typed_unique_violation(self, classifier: ErrorClassifier) -> None:
        """Test typed error with R6_UNIQUE_VIOLATION."""

        class TypedError(Exception):
            def __init__(self) -> None:
                super().__init__("Unique violation")
                self.error_type = P03ErrorType.R6_UNIQUE_VIOLATION

        error = TypedError()
        assert classifier.classify(error) == P03ErrorCategory.VALIDATION


class TestErrorClassifierHelpers:
    """Tests for ErrorClassifier helper methods."""

    @pytest.fixture
    def classifier(self) -> ErrorClassifier:
        """Create ErrorClassifier instance."""
        return ErrorClassifier()

    def test_is_retriable_true(self, classifier: ErrorClassifier) -> None:
        """Test is_retriable returns True for TRANSIENT."""
        assert classifier.is_retriable(ConnectionError("test"))
        assert classifier.is_retriable(TimeoutError("test"))

    def test_is_retriable_false(self, classifier: ErrorClassifier) -> None:
        """Test is_retriable returns False for non-TRANSIENT."""
        assert not classifier.is_retriable(ValueError("test"))
        assert not classifier.is_retriable(MemoryError("test"))
        assert not classifier.is_retriable(Exception("test"))

    def test_is_fatal_true(self, classifier: ErrorClassifier) -> None:
        """Test is_fatal returns True for FATAL."""
        assert classifier.is_fatal(MemoryError("test"))
        assert classifier.is_fatal(RecursionError("test"))

    def test_is_fatal_false(self, classifier: ErrorClassifier) -> None:
        """Test is_fatal returns False for non-FATAL."""
        assert not classifier.is_fatal(ConnectionError("test"))
        assert not classifier.is_fatal(ValueError("test"))

    def test_should_alert_logic(self, classifier: ErrorClassifier) -> None:
        """Test should_alert returns True for LOGIC."""
        assert classifier.should_alert(Exception("test"))
        assert classifier.should_alert(RuntimeError("test"))

    def test_should_alert_fatal(self, classifier: ErrorClassifier) -> None:
        """Test should_alert returns True for FATAL."""
        assert classifier.should_alert(MemoryError("test"))

    def test_should_alert_false(self, classifier: ErrorClassifier) -> None:
        """Test should_alert returns False for TRANSIENT/VALIDATION."""
        assert not classifier.should_alert(ConnectionError("test"))
        assert not classifier.should_alert(ValueError("test"))


class TestOSErrorClassification:
    """Tests for OSError classification."""

    @pytest.fixture
    def classifier(self) -> ErrorClassifier:
        """Create ErrorClassifier instance."""
        return ErrorClassifier()

    def test_disk_full_is_fatal(self, classifier: ErrorClassifier) -> None:
        """Test disk full OSError classified as FATAL."""
        error = OSError("No space left on device - disk full")
        assert classifier.classify(error) == P03ErrorCategory.FATAL

    def test_no_space_is_fatal(self, classifier: ErrorClassifier) -> None:
        """Test no space OSError classified as FATAL."""
        error = OSError("no space on disk")
        assert classifier.classify(error) == P03ErrorCategory.FATAL

    def test_other_os_error_is_transient(self, classifier: ErrorClassifier) -> None:
        """Test other OSError classified as TRANSIENT."""
        error = OSError("Permission denied")
        assert classifier.classify(error) == P03ErrorCategory.TRANSIENT
