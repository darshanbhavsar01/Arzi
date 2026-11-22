"""Structured logs for Cloud Logging, with patient identifiers scrubbed before they are written.

Every record passes through ``PiiFilter`` at the handler, so a careless log line, an exception
message quoting a document, or an access-log path with a family-link token cannot leak. In the
cloud, records are single-line JSON with ``severity`` and the ``logging.googleapis.com/trace``
field, so Cloud Logging groups them under the request's trace.
"""

import contextvars
import datetime as dt
import json
import logging
import re
import sys
from typing import Any

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)
trace_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("trace", default=None)

REDACTED = "[redacted]"

# Order matters: tokens in paths first, then identifiers. Patterns mirror the redaction step.
_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(/(?:f|api/v1/family)/)[A-Za-z0-9_-]{16,}"), rf"\1{REDACTED}"),
    (re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), REDACTED),  # email
    (re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"), REDACTED),  # PAN
    (re.compile(r"\b\d{4}[ -]?\d{4}[ -]?\d{4}\b"), REDACTED),  # Aadhaar-like
    (re.compile(r"(?:\+91[ -]?)?\b[6-9]\d{4}[ -]?\d{5}\b"), REDACTED),  # Indian mobile
)

# Attributes every LogRecord has; anything else was passed through ``extra=``.
_STANDARD = set(vars(logging.LogRecord("", 0, "", 0, "", None, None))) | {"message", "asctime"}


def scrub(text: str) -> str:
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


class PiiFilter(logging.Filter):
    """Rewrites the message (with its arguments merged in) and string extras, in place."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = scrub(record.getMessage())
        record.args = None
        for key, value in vars(record).items():
            if key not in _STANDARD and isinstance(value, str):
                setattr(record, key, scrub(value))
        if record.exc_info and record.exc_info[1] is not None:
            # Keep the type and frames; the message may quote document text.
            record.exc_text = scrub(logging.Formatter().formatException(record.exc_info))
        return True


class JsonFormatter(logging.Formatter):
    def __init__(self, project: str | None) -> None:
        super().__init__()
        self._project = project

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "severity": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "time": dt.datetime.fromtimestamp(record.created, dt.UTC).isoformat(),
        }
        if (request_id := request_id_var.get()) is not None:
            entry["request_id"] = request_id
        if (trace := trace_var.get()) is not None and self._project:
            entry["logging.googleapis.com/trace"] = f"projects/{self._project}/traces/{trace}"
        entry |= {k: v for k, v in vars(record).items() if k not in _STANDARD}
        if record.exc_text:
            entry["exception"] = record.exc_text
        return json.dumps(entry, default=str, ensure_ascii=False)


def trace_id(header: str | None) -> str | None:
    """The trace ID from ``X-Cloud-Trace-Context: TRACE_ID/SPAN_ID;o=1``."""
    if not header:
        return None
    candidate = header.split("/", 1)[0]
    return candidate if re.fullmatch(r"[0-9a-f]{32}", candidate) else None


class _ArziHandler(logging.StreamHandler):  # type: ignore[type-arg]  # generic in typeshed only
    """Marks the handler this module installed, so configuring twice is a no-op."""


def configure_logging(*, json_output: bool, project: str | None, level: str = "INFO") -> None:
    """One stdout handler on the root logger; uvicorn's loggers propagate to it. Idempotent."""
    root = logging.getLogger()
    if any(isinstance(h, _ArziHandler) for h in root.handlers):
        return
    handler = _ArziHandler(sys.stdout)
    handler.addFilter(PiiFilter())
    handler.setFormatter(
        JsonFormatter(project)
        if json_output
        else logging.Formatter("%(levelname)s %(name)s: %(message)s")
    )
    root.addHandler(handler)
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
