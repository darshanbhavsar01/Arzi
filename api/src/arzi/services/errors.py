"""Service errors with a stable problem slug and HTTP status.

The API turns these into RFC 7807 responses. ``detail`` is written for the user and must never
contain document text or identifiers.
"""

from collections.abc import Iterable


class AppError(Exception):
    status = 400
    slug = "bad-request"
    detail = "The request could not be processed."

    def __init__(self, detail: str | None = None) -> None:
        super().__init__(self.slug)
        if detail is not None:
            self.detail = detail


class ClaimNotFoundError(AppError):
    status, slug, detail = 404, "claim-not-found", "No such claim for this hospital."


class DocumentNotFoundError(AppError):
    status, slug, detail = 404, "document-not-found", "No such document on this claim."


class RunNotFoundError(AppError):
    status, slug, detail = 404, "run-not-found", "No such audit run on this claim."


class FlagNotFoundError(AppError):
    status, slug, detail = 404, "flag-not-found", "No such flag in this claim's audit."


class ShareLinkInvalidError(AppError):
    """One answer for unknown, expired and withdrawn links, so tokens cannot be probed."""

    status, slug, detail = (
        404,
        "share-link-invalid",
        "This link has expired or was withdrawn. Ask the hospital desk for a new one.",
    )


class RateLimitedError(AppError):
    status, slug, detail = (
        429,
        "rate-limited",
        "Too many checks from this connection today. Please try again tomorrow.",
    )


class DemoUnavailableError(AppError):
    status, slug, detail = (
        404,
        "demo-cases-unavailable",
        "Demo cases are not available on this deployment.",
    )


class LineNotFoundError(AppError):
    status, slug, detail = 404, "line-not-found", "No such bill line on this claim."


class ConflictError(AppError):
    status, slug, detail = 409, "concurrent-update", "The claim changed; reload and try again."


class InvalidInputError(AppError):
    status, slug = 422, "invalid-input"


class InvalidStateError(AppError):
    status, slug = 409, "invalid-state"


class ConsentRequiredError(AppError):
    status, slug, detail = (
        409,
        "consent-required",
        "Record the patient's consent before the documents are processed.",
    )


class UploadRejectedError(AppError):
    status, slug = 422, "upload-rejected"


class UnsupportedMediaError(AppError):
    status, slug, detail = 415, "unsupported-media-type", "Upload a PDF, JPEG or PNG file."


class FileTooLargeError(AppError):
    status, slug = 413, "file-too-large"


class BudgetReachedError(AppError):
    status, slug, detail = (
        429,
        "budget-exceeded",
        "Today's AI budget is used up. Live extraction is paused; replay mode still works.",
    )


class NotAuthenticatedError(AppError):
    status, slug, detail = 401, "unauthenticated", "Sign in to continue."


class AppealNotFoundError(AppError):
    status, slug, detail = 404, "appeal-not-found", "No such appeal version on this claim."


class AppealNotSignedError(AppError):
    status, slug, detail = (
        409,
        "appeal-not-signed",
        "A named reviewer must sign this appeal before it can be exported.",
    )


class ForumNotEligibleError(AppError):
    status, slug, detail = 409, "forum-not-eligible", "This forum cannot take the appeal yet."


class AppealGuardrailError(AppError):
    """A person's edit broke the appeal rules (an amount written out, an unknown reference)."""

    status, slug = 422, "appeal-guardrail"

    def __init__(self, violations: Iterable[object]) -> None:
        listed = "; ".join(str(v) for v in violations)
        super().__init__(
            "Write amounts only as placeholders such as {{totals.recoverable}} and cite only "
            f"references in the claim. Problems: {listed}."
        )
