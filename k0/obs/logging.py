"""Structured logging and redaction utilities for the K0 kernel."""

from __future__ import annotations

import json
import logging
import re
import sys
import threading
from contextvars import ContextVar, Token
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence, cast

from .tracing import TracerFactory

__all__ = [
    "StructuredLogFormatter",
    "bind_log_context",
    "configure_structured_logging",
    "current_log_context",
    "reset_log_context",
    "update_log_context",
]


_DEFAULT_SENSITIVE_KEYS: tuple[str, ...] = (
    "email",
    "phone",
    "phone_number",
    "ssn",
    "tax_id",
    "password",
    "secret",
    "access_token",
    "refresh_token",
    "auth_token",
    "api_key",
    "pii",
    "tenant_id",
    "space_id",
    "device_id",
    "mls_group_id",
    "user",
    "user_id",
    "username",
    "actor",
    "subject",
    "customer_id",
    "account_id",
    "subscriber_id",
)
_EMAIL_PATTERN = re.compile(r"(?i)[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}")
_DIGIT_PATTERN = re.compile(r"(?<!\d)(\d{9,})(?!\d)")
_RESERVED_LOG_RECORD_ATTRS: frozenset[str] = frozenset(
    {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "message",
        "asctime",
    }
)


_LOG_CONTEXT: ContextVar[dict[str, Any]] = ContextVar("k0_log_context", default={})


def _normalise_context(values: Mapping[str, Any]) -> dict[str, Any]:
    context: dict[str, Any] = {}
    for key, value in values.items():
        if value is None:
            continue
        key_str = str(key).strip()
        if not key_str:
            continue
        context[key_str] = value
    return context


def current_log_context() -> dict[str, Any]:
    """Return the active structured logging context."""

    return dict(_LOG_CONTEXT.get())


def bind_log_context(**values: Any) -> Token[dict[str, Any]] | None:
    """Bind context values for subsequent log records.

    Returns
    -------
    token:
        Context token that can be passed to `reset_log_context`.
    """

    additions = _normalise_context(values)
    if not additions:
        return None
    merged = current_log_context()
    merged.update(additions)
    return _LOG_CONTEXT.set(merged)


def update_log_context(**values: Any) -> None:
    """Merge additional values into the active log context."""

    additions = _normalise_context(values)
    if not additions:
        return
    merged = current_log_context()
    merged.update(additions)
    _LOG_CONTEXT.set(merged)


def reset_log_context(token: Token[dict[str, Any]] | None) -> None:
    """Reset the log context to the state represented by *token*."""

    if token is not None:
        _LOG_CONTEXT.reset(token)


class _StructuredContextFilter(logging.Filter):
    """Attach cognitive trace identifiers and context metadata to log records."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401 - standard API
        if not getattr(record, "cognitive_trace_id", None):
            trace_id = TracerFactory.current_cognitive_trace_id()
            if trace_id:
                record.cognitive_trace_id = trace_id

        for key, value in current_log_context().items():
            lowered = key.lower()
            if lowered == "cognitive_trace_id":
                if not getattr(record, "cognitive_trace_id", None) and value:
                    record.cognitive_trace_id = value  # type: ignore[assignment]
                continue
            if key in _RESERVED_LOG_RECORD_ATTRS:
                continue
            if not hasattr(record, key):
                setattr(record, key, value)

        return True


_CONFIG_LOCK = threading.Lock()
_configured = False


class StructuredLogFormatter(logging.Formatter):
    """Formatter that emits JSON lines with PII redaction and trace context."""

    def __init__(
        self,
        *,
        sensitive_keys: Iterable[str] | None = None,
        mask: str = "[REDACTED]",
    ) -> None:
        super().__init__()
        self._mask = mask
        keys = {key.lower() for key in _DEFAULT_SENSITIVE_KEYS}
        if sensitive_keys:
            for key in sensitive_keys:
                lowered = str(key).strip().lower()
                if lowered:
                    keys.add(lowered)
        self._sensitive_keys = keys

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401 - docstring inherited
        timestamp = datetime.now(tz=timezone.utc).isoformat()
        message = record.getMessage()
        payload: dict[str, Any] = {
            "timestamp": timestamp,
            "level": record.levelname,
            "logger": record.name,
            "message": self._redact_string(message),
        }

        trace_id = getattr(record, "cognitive_trace_id", None)
        if trace_id:
            payload["cognitive_trace_id"] = str(trace_id)

        span_id = getattr(record, "otelSpanID", None) or getattr(record, "span_id", None)
        if span_id:
            payload["span_id"] = str(span_id)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack_info"] = self._redact_string(record.stack_info)

        context_fields = self._extract_context(record)
        if context_fields:
            payload["context"] = context_fields

        return json.dumps(payload, ensure_ascii=False, default=self._fallback_encoder)

    def _extract_context(self, record: logging.LogRecord) -> dict[str, Any]:
        context: dict[str, Any] = {}
        for key, value in record.__dict__.items():
            if key in _RESERVED_LOG_RECORD_ATTRS or key == "cognitive_trace_id":
                continue
            sanitized = self._sanitize_value(key, value)
            context[key] = sanitized
        return context

    def _sanitize_value(self, key: str, value: Any) -> Any:
        lowered_key = key.lower()
        if lowered_key in self._sensitive_keys:
            return self._mask
        if isinstance(value, Mapping):
            mapping_value = cast(Mapping[Any, Any], value)
            return {
                str(inner_key): self._sanitize_value(str(inner_key), inner_value)
                for inner_key, inner_value in mapping_value.items()
            }
        if isinstance(value, (list, tuple, set)):
            iterable: Sequence[Any] = list(cast(Sequence[Any], value))
            return [self._sanitize_value(key, item) for item in iterable]
        if isinstance(value, str):
            return self._redact_string(value)
        return value

    def _redact_string(self, value: str) -> str:
        redacted = _EMAIL_PATTERN.sub(self._mask, value)
        redacted = _DIGIT_PATTERN.sub(self._mask, redacted)
        return redacted

    @staticmethod
    def _fallback_encoder(obj: Any) -> Any:
        if isinstance(obj, datetime):
            return obj.isoformat()
        try:
            return str(obj)
        except Exception:  # pragma: no cover - defensive fallback
            return "<unserializable>"


def configure_structured_logging(
    *,
    level: str = "INFO",
    stream: Any | None = None,
    sensitive_keys: Iterable[str] | None = None,
    mask: str = "[REDACTED]",
    force: bool = False,
) -> None:
    """Install the structured logging handler on the root logger."""

    global _configured
    with _CONFIG_LOCK:
        if _configured and not force:
            return

        root_logger = logging.getLogger()
        root_logger.handlers.clear()

        handler_stream = stream or sys.stdout
        handler = logging.StreamHandler(handler_stream)
        formatter = StructuredLogFormatter(
            sensitive_keys=sensitive_keys,
            mask=mask,
        )
        handler.setFormatter(formatter)
        handler.addFilter(_StructuredContextFilter())
        root_logger.addHandler(handler)
        root_logger.setLevel(level.upper())

        logging.captureWarnings(True)

        for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
            logger = logging.getLogger(logger_name)
            logger.handlers.clear()
            logger.propagate = True

        # Completely disable high-volume operational loggers
        for noisy in (
            "uvicorn.access",
            "k0.drivers.sse_outbox_driver",
            "k0.policy.pep_syscall",
        ):
            lg = logging.getLogger(noisy)
            lg.setLevel(logging.CRITICAL + 1)
            lg.propagate = False

        markdown_logger = logging.getLogger("markdown_it")
        markdown_logger.handlers.clear()
        markdown_logger.propagate = True
        markdown_logger.setLevel(logging.INFO)

    _configured = True
