"""Request IDs: one per request, echoed in ``X-Request-ID`` and in every problem response.

An inbound ID is honoured only if it looks like one we would generate, so clients cannot inject
arbitrary text into logs through the header.
"""

import re
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response

from arzi.observability.logging import request_id_var, trace_id, trace_var

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_ID = re.compile(r"^[A-Za-z0-9-]{8,64}$")


def get_request_id(request: Request) -> str | None:
    value = getattr(request.state, "request_id", None)
    return value if isinstance(value, str) else None


async def request_id_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    inbound = request.headers.get(REQUEST_ID_HEADER, "")
    request_id = inbound if _VALID_ID.fullmatch(inbound) else uuid.uuid4().hex
    request.state.request_id = request_id
    # Log lines written while handling this request carry its ID and Cloud Trace ID.
    id_token = request_id_var.set(request_id)
    trace_token = trace_var.set(trace_id(request.headers.get("x-cloud-trace-context")))
    try:
        response = await call_next(request)
    finally:
        request_id_var.reset(id_token)
        trace_var.reset(trace_token)
    response.headers[REQUEST_ID_HEADER] = request_id
    return response
