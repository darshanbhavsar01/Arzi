"""PII scrubbing in logs, JSON log shape with trace correlation, and the token bucket."""

import io
import json
import logging

import pytest

from arzi.api.security import TokenBucketLimiter
from arzi.observability.logging import (
    JsonFormatter,
    PiiFilter,
    configure_logging,
    request_id_var,
    scrub,
    trace_id,
    trace_var,
)


@pytest.mark.parametrize(
    "text",
    [
        "patient email ramesh.parmar@example.in",
        "aadhaar 1234 5678 9012",
        "aadhaar 123456789012",
        "PAN ABCDE1234F",
        "mobile +91 98765 43210",
        "mobile 9876543210",
        'GET /api/v1/family/AbCdEfGhIjKlMnOpQrStUvWxYz0123456789_-xyz/view HTTP/1.1" 200',
        "GET /f/AbCdEfGhIjKlMnOpQrStUvWxYz0123456789_-xyz",
    ],
)
def test_identifiers_and_link_tokens_are_scrubbed(text: str) -> None:
    cleaned = scrub(text)
    assert "[redacted]" in cleaned
    for secret in ("ramesh", "5678", "ABCDE1234F", "43210", "9876543210", "AbCdEfGh"):
        assert secret not in cleaned


def test_ids_amounts_and_dates_survive() -> None:
    text = "claim ARZ-2026-1E842D at risk 6788750 paise on 2026-11-20, run run-cd0f07691e28"
    assert scrub(text) == text


def _record(msg: str, *args: object, **extra: object) -> logging.LogRecord:
    record = logging.LogRecord("arzi.test", logging.WARNING, __file__, 1, msg, args, None)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_filter_scrubs_arguments_extras_and_exceptions() -> None:
    record = _record("upload from %s", "ramesh@example.in", note="call 9876543210")
    try:
        raise ValueError("document says PAN ABCDE1234F")
    except ValueError:
        import sys

        record.exc_info = sys.exc_info()
    assert PiiFilter().filter(record)
    assert record.getMessage() == "upload from [redacted]"
    assert record.note == "call [redacted]"  # type: ignore[attr-defined]  # set via extra
    assert record.exc_text is not None
    assert "ValueError" in record.exc_text
    assert "ABCDE1234F" not in record.exc_text


def test_json_lines_carry_severity_request_and_trace() -> None:
    record = _record("claim erased", claim_id="ARZ-1")
    request_token = request_id_var.set("req-12345678")
    trace_token = trace_var.set("0123456789abcdef0123456789abcdef")
    try:
        line = json.loads(JsonFormatter("proj-1").format(record))
    finally:
        request_id_var.reset(request_token)
        trace_var.reset(trace_token)
    assert line["severity"] == "WARNING"
    assert line["message"] == "claim erased"
    assert line["claim_id"] == "ARZ-1"
    assert line["request_id"] == "req-12345678"
    assert line["logging.googleapis.com/trace"] == (
        "projects/proj-1/traces/0123456789abcdef0123456789abcdef"
    )
    assert "logging.googleapis.com/trace" not in json.loads(JsonFormatter(None).format(record))


def test_trace_header_parsing() -> None:
    assert trace_id("0123456789abcdef0123456789abcdef/123;o=1") == (
        "0123456789abcdef0123456789abcdef"
    )
    assert trace_id("not-a-trace/1") is None
    assert trace_id(None) is None


def test_configure_logging_is_idempotent_and_scrubs(monkeypatch: pytest.MonkeyPatch) -> None:
    root = logging.getLogger()
    saved = list(root.handlers)
    stream = io.StringIO()
    monkeypatch.setattr("sys.stdout", stream)
    root.handlers = [h for h in root.handlers if type(h).__name__ != "_ArziHandler"]
    try:
        configure_logging(json_output=True, project=None)
        configure_logging(json_output=True, project=None)
        ours = [h for h in root.handlers if type(h).__name__ == "_ArziHandler"]
        assert len(ours) == 1
        logging.getLogger("uvicorn.access").warning("GET /f/%s", "A" * 40)
        assert json.loads(stream.getvalue().splitlines()[-1])["message"] == "GET /f/[redacted]"
    finally:
        root.handlers = saved


def test_token_bucket_refills_over_time_and_isolates_clients() -> None:
    now = [0.0]
    limiter = TokenBucketLimiter(b"k", rate_per_minute=60, burst=2, clock=lambda: now[0])
    assert limiter.take("10.0.0.1") == 0
    assert limiter.take("10.0.0.1") == 0
    assert limiter.take("10.0.0.1") == pytest.approx(1.0)
    assert limiter.take("10.0.0.2") == 0  # another client has its own bucket
    now[0] += 1.0
    assert limiter.take("10.0.0.1") == 0  # one token back after a second


def test_token_bucket_forgets_the_least_recent_client_beyond_its_bound() -> None:
    limiter = TokenBucketLimiter(
        b"k", rate_per_minute=60, burst=1, clock=lambda: 0.0, max_clients=2
    )
    limiter.take("a")
    limiter.take("b")
    limiter.take("c")  # evicts "a"
    assert limiter.take("a") == 0  # a fresh bucket again
