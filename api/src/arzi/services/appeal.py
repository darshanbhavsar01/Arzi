"""Appeals: draft (AppealDrafter), edit into new versions, submit for review, sign, export.

Human in the loop, enforced here and in the claim state machine: an appeal goes
``draft → in_review → signed → exported``; only a signed version can be exported; signing stores
the reviewer's name and role and the SHA-256 of exactly the content they signed; any edit makes
a new draft version that needs a fresh signature. Disputed items, amounts and the relief total
come from the rules engine; model-written and person-written prose both pass the guardrails.
"""

import datetime as dt
import hashlib
import json
from collections.abc import Awaitable, Callable, Sequence
from typing import Annotated, Any, Literal

import anyio
from pydantic import BaseModel, ConfigDict, Field

from arzi.agents import appeal_drafter
from arzi.agents.appeal_drafter import AppealJob, disputed, insurer_reason
from arzi.agents.guardrails import Violation, check_prose, placeholder_values, try_render
from arzi.agents.nodes import ModelSettings, ReasoningTask
from arzi.agents.schemas import AppealDraftOutput
from arzi.domain.enums import (
    AppealForum,
    AppealStatus,
    CitationStatus,
    ClaimMode,
    ClaimStatus,
    ReasoningStatus,
)
from arzi.domain.models import (
    AppealContent,
    AppealItem,
    AppealSignature,
    AppealSummary,
    AppealVersion,
    AuditResult,
    ClaimFacts,
    ClaimRecord,
    LlmCall,
    Prose,
)
from arzi.domain.money import format_inr
from arzi.domain.state import ClaimEvent, transition
from arzi.rules.context import POLICY_REF_PREFIX
from arzi.rules.disputes import PROP_WRONGLY_APPLIED
from arzi.rules.forums import ForumOption, GroComplaint, forum_options
from arzi.rules.non_payable import SUBSUMED_ITEM
from arzi.rules.reference import citations
from arzi.rules.waiting import MORATORIUM, WAITING_REJECTION_INVALID
from arzi.services.appeal_pdf import Letter, LetterItem, render_letter
from arzi.services.cost_ledger import IST
from arzi.services.errors import (
    AppealGuardrailError,
    AppealNotFoundError,
    AppealNotSignedError,
    ClaimNotFoundError,
    ConflictError,
    ForumNotEligibleError,
    InvalidStateError,
)
from arzi.services.ports import AuditLogEntry, ClaimRepository, ConcurrentUpdateError, Principal

Clock = Callable[[], dt.datetime]
Reasoner = Callable[[ReasoningTask[Any], ModelSettings, list[LlmCall]], Awaitable[None]]

_DRAFTABLE = {
    ClaimStatus.AUDITED: (ClaimEvent.DRAFT_APPEAL,),
    ClaimStatus.APPEAL_DRAFTED: (),
    ClaimStatus.IN_REVIEW: (ClaimEvent.REQUEST_CHANGES,),
    ClaimStatus.SIGNED: (ClaimEvent.REVISE,),
}
_CHECKED = {ReasoningStatus.PASSED, ReasoningStatus.RETRIED}
_ENCLOSURES = (
    ("insurer_letter", "Copy of the insurer's letter"),
    ("policy", "Policy schedule and wording"),
    ("itemised_bill", "Itemised hospital bill"),
    ("discharge_summary", "Discharge summary"),
    ("investigation_reports", "Investigation reports"),
    ("implant_invoice", "Implant invoice and sticker"),
)
_ITEM_TITLES = {
    PROP_WRONGLY_APPLIED: "Proportionate deduction on items it cannot apply to",
    SUBSUMED_ITEM: "Item deducted that is part of room or procedure charges",
    WAITING_REJECTION_INVALID: "Rejection under a waiting period that had ended",
    MORATORIUM: "Rejection after the moratorium period",
}
_ADDRESSEE = {
    AppealForum.INSURER_GRO: ("The Grievance Redressal Officer", "{insurer}"),
    AppealForum.BIMA_BHAROSA: (
        "Bima Bharosa grievance portal",
        "Insurance Regulatory and Development Authority of India",
        "Complaint against {insurer}",
    ),
    AppealForum.OMBUDSMAN: (
        "The Insurance Ombudsman",
        "Office of the Insurance Ombudsman (jurisdiction to be confirmed)",
        "Complaint against {insurer}",
    ),
}
_IDENTITY_FIELDS = (
    ("[POLICY_NUMBER-", "Policy number"),
    ("[MEMBER_ID-", "Member ID"),
    ("[CLAIM_NUMBER-", "Insurer claim number"),
)
_FALLBACK = AppealDraftOutput(
    subject="Request to review the claim decision",
    facts="",
    items=[],
    relief="We request that the insurer pay {{totals.recoverable}}.",
    citations=[],
)


class _Body(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ArgumentEdit(_Body):
    flag_id: str = Field(max_length=200)
    argument: str = Field(max_length=6000)


class AppealEdit(_Body):
    """A reviewer's changes; omitted sections stay as they are. Amounts stay placeholders."""

    subject: Annotated[str, Field(max_length=6000)] | None = None
    facts: Annotated[str, Field(max_length=6000)] | None = None
    relief: Annotated[str, Field(max_length=6000)] | None = None
    arguments: list[ArgumentEdit] | None = None


class SignRequest(_Body):
    reviewer_name: str = Field(min_length=2, max_length=120)
    reviewer_role: str = Field(min_length=2, max_length=120, description="e.g. 'TPA desk manager'")
    declaration: Literal[True] = Field(
        description="I have read this appeal and confirm it is accurate to the best of my "
        "knowledge."
    )


def content_sha256(appeal: AppealVersion) -> str:
    """SHA-256 of what a reviewer signs: the rendered letter content, canonically serialised.

    Identity fields (names, policy and claim numbers) are not part of it; they are filled from
    the restricted identity vault only when the signed letter is printed.
    """
    c = appeal.content
    payload = {
        "claim_id": appeal.claim_id,
        "version": appeal.version,
        "forum": str(appeal.forum),
        "subject": c.subject.text,
        "facts": c.facts.text,
        "items": [
            {
                "flag_id": i.flag_id,
                "amount": i.amount,
                "insurer_reason": i.insurer_reason,
                "argument": i.argument.text,
                "citations": list(i.citations),
            }
            for i in c.items
        ],
        "relief": c.relief.text,
        "relief_amount": c.relief_amount,
        "enclosures": list(c.enclosures),
    }
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def enclosures(facts: ClaimFacts) -> tuple[str, ...]:
    present = {str(kind) for kind in facts.documents_present}
    if facts.insurer_letter is not None:
        present.add("insurer_letter")
    return tuple(label for kind, label in _ENCLOSURES if kind in present)


def compose(facts: ClaimFacts, result: AuditResult, output: AppealDraftOutput) -> AppealContent:
    """Engine-owned structure, drafted prose; every amount rendered from the engine."""
    values = placeholder_values(facts, result)

    def prose(template: str) -> Prose:
        return Prose(template=template, text=try_render(template, values))

    arguments = {item.flag_id: item for item in output.items}
    items = []
    for flag in disputed(result):
        drafted = arguments.get(flag.flag_id)
        extra = drafted.citations if drafted else []
        items.append(
            AppealItem(
                flag_id=flag.flag_id,
                rule_id=flag.rule_id,
                amount=flag.recoverable,
                amount_ref=f"flag.{flag.flag_id}.recoverable",
                insurer_reason=insurer_reason(flag, facts),
                argument=prose(drafted.argument if drafted else ""),
                citations=tuple(dict.fromkeys((*flag.citation_refs, *extra))),
            )
        )
    return AppealContent(
        subject=prose(output.subject),
        facts=prose(output.facts),
        items=tuple(items),
        relief=prose(output.relief),
        relief_amount=result.totals.recoverable_on_appeal,
        enclosures=enclosures(facts),
    )


def citation_label(ref: str) -> str:
    """How a reference reads in a letter: the clause number, or the regulation's title (plus its
    circular number once that is verified)."""
    if ref.startswith(POLICY_REF_PREFIX):
        return f"Policy clause {ref.removeprefix(POLICY_REF_PREFIX)}"
    entry = citations().get(ref)
    if entry is None:  # pragma: no cover - the whitelist keeps unknown refs out
        return ref
    verified = entry.status is CitationStatus.VERIFIED
    return f"{entry.title} ({entry.ref})" if verified else entry.title


def identity_fields(vault: dict[str, str], patient: str) -> list[tuple[str, str]]:
    """Patient, policy, member and claim numbers for the letter's reference block."""
    found = [("Patient", vault[patient])] if patient in vault else []
    for prefix, label in _IDENTITY_FIELDS:
        alias = next((a for a in sorted(vault) if a.startswith(prefix)), None)
        if alias is not None:
            found.append((label, vault[alias]))
    return found


def letter_for(claim: ClaimRecord, appeal: AppealVersion, vault: dict[str, str]) -> Letter:
    """The printable letter. Pseudonyms in the reviewed text are replaced by the identifiers
    they stand for, from the restricted vault, only here."""
    facts, signature = claim.facts, appeal.signature
    if facts is None or signature is None:  # pragma: no cover - checked by the caller
        raise InvalidStateError("Only a signed appeal of an audited claim can be printed.")
    pseudonyms = sorted(vault, key=len, reverse=True)

    def reveal(text: str | None) -> str:
        shown = text or ""
        for alias in pseudonyms:
            shown = shown.replace(alias, vault[alias])
        return shown

    references = [
        *identity_fields(vault, facts.patient.redacted_id),
        ("Hospital reference", f"{claim.claim_id}, appeal version {appeal.version}"),
    ]
    lines = {line.line_id: line.description for line in facts.bill_lines}
    flags = {f.flag_id: f for f in claim.audit.flags} if claim.audit else {}
    items = []
    for item in appeal.content.items:
        flag = flags.get(item.flag_id)
        described = [lines[i] for i in (flag.lines if flag else ()) if i in lines]
        title = _ITEM_TITLES.get(item.rule_id, item.rule_id.replace("_", " ").capitalize())
        items.append(
            LetterItem(
                title=title,
                lines=[reveal(d) for d in described],
                amount=format_inr(item.amount, always_paise=True),
                insurer_reason=item.insurer_reason,
                argument=reveal(item.argument.text),
                citations=[citation_label(c) for c in item.citations],
            )
        )
    signed = signature.signed_at.astimezone(IST).date()
    on = f"{signed.day} {signed:%B %Y}"
    insurer = facts.policy.insurer
    return Letter(
        hospital_name=facts.hospital.name,
        hospital_city=facts.hospital.city,
        addressee=[line.format(insurer=insurer) for line in _ADDRESSEE[appeal.forum]],
        date=on,
        references=references,
        subject=reveal(appeal.content.subject.text),
        facts=reveal(appeal.content.facts.text),
        items=items,
        relief=reveal(appeal.content.relief.text),
        enclosures=list(appeal.content.enclosures),
        reviewer_name=signature.reviewer_name,
        reviewer_role=signature.reviewer_role,
        signed_on=on,
        content_sha256=signature.content_sha256,
    )


def readiness(appeal: AppealVersion) -> list[str]:
    """What still stops this version going to review (empty when it is ready)."""
    c = appeal.content
    gaps = []
    if appeal.drafting not in _CHECKED:
        gaps.append("the draft did not pass its checks; edit it first")
    sections = [c.subject, c.facts, c.relief, *(i.argument for i in c.items)]
    if any(not (p.text or "").strip() for p in sections):
        gaps.append("every section needs text")
    return gaps


class AppealService:
    def __init__(
        self,
        repo: ClaimRepository,
        models: ModelSettings,
        *,
        clock: Clock,
        reason: Reasoner,
    ) -> None:
        self._repo = repo
        self._models = models
        self._clock = clock
        self._reason = reason

    # ------------------------------------------------------------------ reads

    async def forums(
        self, principal: Principal, claim_id: str, complaint: GroComplaint | None
    ) -> tuple[ForumOption, ...]:
        claim = await self._claim(principal, claim_id)
        _, result = self._audited(claim)
        return self._options(result, complaint)

    async def versions(self, principal: Principal, claim_id: str) -> list[AppealVersion]:
        claim = await self._claim(principal, claim_id)
        known = {s.version for s in claim.appeals}
        stored = await self._repo.list_appeals(principal.hospital_id, claim_id)
        return [a for a in stored if a.version in known]

    async def get(self, principal: Principal, claim_id: str, version: int) -> AppealVersion:
        await self._claim(principal, claim_id)
        appeal = await self._repo.get_appeal(principal.hospital_id, claim_id, version)
        if appeal is None:
            raise AppealNotFoundError
        return appeal

    # ------------------------------------------------------------------ draft

    async def draft(
        self,
        principal: Principal,
        claim_id: str,
        forum: AppealForum,
        complaint: GroComplaint | None,
        idempotency_key: str | None,
    ) -> AppealVersion:
        claim = await self._claim(principal, claim_id)
        if idempotency_key:
            for appeal in await self.versions(principal, claim_id):
                if appeal.idempotency_key == idempotency_key:
                    return appeal
        facts, result = self._audited(claim)
        if claim.mode is ClaimMode.PRE_SUBMISSION or not disputed(result):
            raise InvalidStateError(
                "Nothing to appeal: the audit found no insurer decision to dispute."
            )
        option = next(o for o in self._options(result, complaint) if o.forum is forum)
        if not option.eligible:
            raise ForumNotEligibleError(option.reason)
        status = self._drafting_status(claim)

        job = AppealJob(facts=facts, audit=result, forum=forum)
        calls: list[LlmCall] = []
        await self._reason(appeal_drafter.task(job), self._models, calls)
        output = job.output if job.output is not None else _FALLBACK
        appeal = AppealVersion(
            claim_id=claim_id,
            version=max((s.version for s in claim.appeals), default=0) + 1,
            forum=forum,
            content=compose(facts, result, output),
            drafting=job.status,
            prompt_ref=job.prompt.ref,
            violations=tuple(str(v) for v in job.violations),
            idempotency_key=idempotency_key,
            created_by=principal.user_id,
            created_at=self._clock(),
        )
        await self._store(principal, claim, appeal, status)
        await self._log(
            principal,
            claim_id,
            "appeal.drafted",
            version=appeal.version,
            forum=str(forum),
            prompt=appeal.prompt_ref,
            outcome=str(job.status),
            model_calls=len(calls),
        )
        return appeal

    # ------------------------------------------------------------------ edit / review / sign

    async def edit(
        self, principal: Principal, claim_id: str, version: int, edit: AppealEdit
    ) -> AppealVersion:
        claim, base = await self._latest(principal, claim_id, version)
        facts, result = self._audited(claim)
        status = self._drafting_status(claim)
        policy = AppealJob(facts=facts, audit=result, forum=base.forum).prose_policy()
        content = base.content
        changed = {k: v for k, v in edit.model_dump(exclude={"arguments"}).items() if v is not None}
        arguments = {a.flag_id: a.argument for a in edit.arguments or ()}
        unknown = set(arguments) - {i.flag_id for i in content.items}
        violations: list[Violation] = [Violation("unexpected_flag", "arguments")] if unknown else []
        values = placeholder_values(facts, result)

        def revised(where: str, old: Prose, new: str | None) -> Prose:
            template = old.template if new is None else new
            violations.extend(check_prose(template, policy, where))
            return Prose(template=template, text=try_render(template, values))

        content = content.model_copy(
            update={
                "subject": revised("subject", content.subject, changed.get("subject")),
                "facts": revised("facts", content.facts, changed.get("facts")),
                "relief": revised("relief", content.relief, changed.get("relief")),
                "items": tuple(
                    item.model_copy(
                        update={
                            "argument": revised(
                                f"arguments[{item.flag_id}]",
                                item.argument,
                                arguments.get(item.flag_id),
                            )
                        }
                    )
                    for item in content.items
                ),
            }
        )
        if violations:
            raise AppealGuardrailError(violations)
        appeal = AppealVersion(
            claim_id=claim_id,
            version=version + 1,
            forum=base.forum,
            content=content,
            drafting=ReasoningStatus.PASSED,
            based_on=version,
            created_by=principal.user_id,
            created_at=self._clock(),
        )
        await self._store(principal, claim, appeal, status)
        await self._log(
            principal, claim_id, "appeal.edited", version=appeal.version, based_on=version
        )
        return appeal

    async def submit(self, principal: Principal, claim_id: str, version: int) -> AppealVersion:
        claim, appeal = await self._latest(principal, claim_id, version)
        if appeal.status is not AppealStatus.DRAFT:
            raise InvalidStateError(f"Only a draft can be submitted; this one is {appeal.status}.")
        gaps = readiness(appeal)
        if gaps:
            raise InvalidStateError("Not ready for review: " + "; ".join(gaps) + ".")
        appeal = appeal.model_copy(update={"status": AppealStatus.IN_REVIEW})
        await self._store(
            principal, claim, appeal, transition(claim.status, ClaimEvent.SUBMIT_FOR_REVIEW)
        )
        await self._log(principal, claim_id, "appeal.submitted", version=version)
        return appeal

    async def sign(
        self, principal: Principal, claim_id: str, version: int, request: SignRequest
    ) -> AppealVersion:
        claim, appeal = await self._latest(principal, claim_id, version)
        if appeal.status is not AppealStatus.IN_REVIEW:
            raise InvalidStateError("Submit the appeal for review before signing it.")
        digest = content_sha256(appeal)
        signature = AppealSignature(
            reviewer_name=request.reviewer_name,
            reviewer_role=request.reviewer_role,
            signed_by=principal.user_id,
            signed_at=self._clock(),
            content_sha256=digest,
        )
        appeal = appeal.model_copy(update={"status": AppealStatus.SIGNED, "signature": signature})
        await self._store(principal, claim, appeal, transition(claim.status, ClaimEvent.SIGN))
        await self._log(principal, claim_id, "appeal.signed", version=version, sha256=digest)
        return appeal

    async def signed_for_export(
        self, principal: Principal, claim_id: str, version: int
    ) -> tuple[ClaimRecord, AppealVersion]:
        """The signed version, its integrity checked; export is impossible before signing."""
        claim = await self._claim(principal, claim_id)
        appeal = await self.get(principal, claim_id, version)
        signature = appeal.signature
        if appeal.status not in {AppealStatus.SIGNED, AppealStatus.EXPORTED} or signature is None:
            raise AppealNotSignedError
        if content_sha256(appeal) != signature.content_sha256:  # pragma: no cover - immutable
            raise ConflictError("The appeal changed after it was signed.")
        return claim, appeal

    async def mark_exported(
        self, principal: Principal, claim: ClaimRecord, appeal: AppealVersion
    ) -> AppealVersion:
        """First export moves the appeal and claim to ``exported``; later exports reprint it."""
        if appeal.status is AppealStatus.EXPORTED:
            return appeal
        appeal = appeal.model_copy(
            update={"status": AppealStatus.EXPORTED, "exported_at": self._clock()}
        )
        await self._store(principal, claim, appeal, transition(claim.status, ClaimEvent.EXPORT))
        signature = appeal.signature
        await self._log(
            principal,
            claim.claim_id,
            "appeal.exported",
            version=appeal.version,
            sha256=signature.content_sha256 if signature else None,
        )
        return appeal

    async def export(
        self, principal: Principal, claim_id: str, version: int
    ) -> tuple[bytes, AppealVersion]:
        """The signed letter as a PDF. Same signed version, same bytes, every time."""
        claim, appeal = await self.signed_for_export(principal, claim_id, version)
        vault = await self._repo.get_identity_vault(principal.hospital_id, claim_id)
        pdf = await anyio.to_thread.run_sync(render_letter, letter_for(claim, appeal, vault))
        return pdf, await self.mark_exported(principal, claim, appeal)

    # ------------------------------------------------------------------ helpers

    async def _claim(self, principal: Principal, claim_id: str) -> ClaimRecord:
        claim = await self._repo.get_claim(principal.hospital_id, claim_id)
        if claim is None:
            raise ClaimNotFoundError
        return claim

    @staticmethod
    def _audited(claim: ClaimRecord) -> tuple[ClaimFacts, AuditResult]:
        if claim.facts is None or claim.audit is None:
            raise InvalidStateError("Audit the claim before drafting an appeal.")
        return claim.facts, claim.audit

    def _options(
        self, result: AuditResult, complaint: GroComplaint | None
    ) -> tuple[ForumOption, ...]:
        today = self._clock().astimezone(IST).date()
        return forum_options(
            relief=result.totals.recoverable_on_appeal, today=today, complaint=complaint
        )

    @staticmethod
    def _drafting_status(claim: ClaimRecord) -> ClaimStatus:
        if claim.status not in _DRAFTABLE:
            raise InvalidStateError(
                f"An appeal cannot be drafted for a claim that is {claim.status}."
            )
        status = claim.status
        for event in _DRAFTABLE[status]:
            status = transition(status, event)
        return status

    async def _latest(
        self, principal: Principal, claim_id: str, version: int
    ) -> tuple[ClaimRecord, AppealVersion]:
        claim = await self._claim(principal, claim_id)
        appeal = await self.get(principal, claim_id, version)
        latest = max(s.version for s in claim.appeals)
        if version != latest:
            raise InvalidStateError(f"Work on the latest version (v{latest}).")
        return claim, appeal

    async def _store(
        self,
        principal: Principal,
        claim: ClaimRecord,
        appeal: AppealVersion,
        status: ClaimStatus,
    ) -> None:
        summary = AppealSummary(
            appeal_id=f"v{appeal.version}",
            forum=appeal.forum,
            version=appeal.version,
            status=appeal.status,
            content_sha256=appeal.signature.content_sha256 if appeal.signature else None,
        )
        others: Sequence[AppealSummary] = [s for s in claim.appeals if s.version != appeal.version]
        updated = claim.model_copy(
            update={
                "status": status,
                "appeals": tuple(sorted((*others, summary), key=lambda s: s.version)),
                "updated_at": self._clock(),
            }
        )
        # The version first: if the claim write then loses a race, the version is not listed
        # (listing follows the claim's summaries) and its number is reused by the next write.
        await self._repo.save_appeal(principal.hospital_id, appeal)
        try:
            await self._repo.save_claim(updated)
        except ConcurrentUpdateError:
            raise ConflictError from None

    async def _log(
        self, principal: Principal, claim_id: str, action: str, **detail: str | int | None
    ) -> None:
        entry = AuditLogEntry(
            at=self._clock(), actor=principal.user_id, action=action, detail=dict(detail)
        )
        await self._repo.append_audit_log(principal.hospital_id, claim_id, entry)
