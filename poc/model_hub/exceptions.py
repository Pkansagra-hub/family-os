"""
Custom exceptions for the Model Hub.
"""

from typing import Optional


class ModelHubError(Exception):
    """Base exception for Model Hub operations."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ProviderError(ModelHubError):
    """Exception raised when a provider operation fails."""

    def __init__(self, provider: str, message: str, details: Optional[dict] = None):
        super().__init__(f"Provider '{provider}' error: {message}", details)
        self.provider = provider


class ConfigurationError(ModelHubError):
    """Exception raised when configuration is invalid."""

    def __init__(
        self, message: str, field: Optional[str] = None, details: Optional[dict] = None
    ):
        super().__init__(f"Configuration error: {message}", details)
        self.field = field


class ValidationError(ModelHubError):
    """Exception raised when input validation fails."""

    def __init__(
        self, message: str, field: Optional[str] = None, details: Optional[dict] = None
    ):
        super().__init__(f"Validation error: {message}", details)
        self.field = field


class RateLimitError(ProviderError):
    """Exception raised when rate limits are exceeded."""

    def __init__(
        self,
        provider: str,
        retry_after: Optional[int] = None,
        details: Optional[dict] = None,
    ):
        message = "Rate limit exceeded"
        if retry_after:
            message += f". Retry after {retry_after} seconds"
        super().__init__(provider, message, details)
        self.retry_after = retry_after


class AuthenticationError(ProviderError):
    """Exception raised when authentication fails."""

    def __init__(
        self,
        provider: str,
        message: str = "Authentication failed",
        details: Optional[dict] = None,
    ):
        super().__init__(provider, message, details)


class ModelNotFoundError(ProviderError):
    """Exception raised when a requested model is not available."""

    def __init__(self, provider: str, model: str, details: Optional[dict] = None):
        super().__init__(provider, f"Model '{model}' not found", details)
        self.model = model


class TimeoutError(ProviderError):
    """Exception raised when operations timeout."""

    def __init__(self, provider: str, timeout: float, details: Optional[dict] = None):
        super().__init__(provider, f"Operation timed out after {timeout}s", details)
        self.timeout = timeout
