"""RFC 7807 problem responses.

Every error leaves the API as ``application/problem+json`` with a stable ``type`` slug the web
client can switch on, and the request ID so a user can quote it to support. Exception messages
and stack traces never reach the response body.
"""

import logging
import traceback
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException as StarletteHTTPException

from arzi.api.request_id import REQUEST_ID_HEADER, get_request_id

PROBLEM_MEDIA_TYPE = "application/problem+json"
_TYPE_BASE = "https://arzi.app/problems/"

logger = logging.getLogger(__name__)


class Problem(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: str
    title: str
    status: int
    detail: str | None = None
    request_id: str | None = None


def problem_response(
    request: Request, status: int, slug: str, detail: str | None = None
) -> JSONResponse:
    """Build a problem response; ``slug`` is the stable machine-readable error identifier."""
    request_id = get_request_id(request)
    problem = Problem(
        type=f"{_TYPE_BASE}{slug}",
        title=HTTPStatus(status).phrase,
        status=status,
        detail=detail,
        request_id=request_id,
    )
    # Set here as well as in the middleware: Starlette runs the catch-all handler outside the
    # HTTP middleware stack, so 500 responses would otherwise lose the header.
    headers = {REQUEST_ID_HEADER: request_id} if request_id else None
    return JSONResponse(
        problem.model_dump(exclude_none=True),
        status_code=status,
        media_type=PROBLEM_MEDIA_TYPE,
        headers=headers,
    )


async def _http_exception(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)  # noqa: S101 - registered for this type only
    slug = HTTPStatus(exc.status_code).phrase.lower().replace(" ", "-")
    detail = exc.detail if isinstance(exc.detail, str) else None
    return problem_response(request, exc.status_code, slug, detail)


async def _validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)  # noqa: S101 - registered for this type only
    # Field locations are safe to echo; input values may contain document text, so omit them.
    fields = sorted({".".join(str(p) for p in err["loc"]) for err in exc.errors()})
    return problem_response(
        request, 422, "validation-error", f"Invalid fields: {', '.join(fields)}"
    )


async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    # Log the type and stack frames but not the message: exception text can quote patient data.
    logger.error(
        "unhandled %s\n%s",
        type(exc).__name__,
        "".join(traceback.format_tb(exc.__traceback__)),
        extra={"request_id": get_request_id(request)},
    )
    return problem_response(request, 500, "internal-error", "An unexpected error occurred.")


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, _http_exception)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(Exception, _unhandled)
