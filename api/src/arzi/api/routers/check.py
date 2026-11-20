"""The free "Check my rejection" (public, rate-limited, budget-guarded)."""

from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, Request, UploadFile, status

from arzi.api.deps import ServicesDep, SettingsDep
from arzi.domain.enums import ClaimMode
from arzi.services.errors import FileTooLargeError, InvalidInputError
from arzi.services.public_check import CheckFile, CheckStarted, Role

router = APIRouter(prefix="/api/v1/check", tags=["check"])


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def start_check(
    request: Request,
    services: ServicesDep,
    settings: SettingsDep,
    mode: Annotated[Literal["post_deduction", "post_rejection"], Form()],
    consent: Annotated[bool, Form(description="Consent to process these documents")],
    letter: Annotated[UploadFile, File(description="The insurer's letter")],
    bill: Annotated[UploadFile, File(description="The final itemised hospital bill")],
    policy: Annotated[list[UploadFile], File(description="Policy schedule and/or wording")],
    discharge: Annotated[UploadFile | None, File(description="Discharge summary")] = None,
    given_by: Annotated[str, Form(max_length=120)] = "policyholder",
) -> CheckStarted:
    """Upload, audit and get a private link to the result (a 7-day family view)."""
    if not consent:
        raise InvalidInputError("Consent is needed before Arzi reads the documents.")
    limit = settings.max_upload_mb * 1024 * 1024
    uploads: list[tuple[Role, UploadFile]] = [("letter", letter), ("bill", bill)]
    uploads += [("policy", p) for p in policy]
    if discharge is not None:
        uploads.append(("discharge", discharge))
    files = []
    for role, upload in uploads:
        data = await upload.read(limit + 1)
        if len(data) > limit:
            raise FileTooLargeError(f"Files can be at most {settings.max_upload_mb} MB.")
        files.append(CheckFile(role=role, filename=upload.filename or role, data=data))
    address = request.client.host if request.client else "unknown"
    return await services.public_check.start(address, ClaimMode(mode), files, given_by)
