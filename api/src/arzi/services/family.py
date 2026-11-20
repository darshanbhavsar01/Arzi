"""The family experience: explanations in Gujarati, Hindi and English, narrated audio, and share
links that open a read-only view of the claim for the patient's family.

A link carries a random 32-byte token; only its SHA-256 is stored, it expires after a week and
the desk can withdraw it. The family view holds no identifiers and no document content: only the
procedure, dates, engine figures and the checked explanations.
"""

import datetime as dt
import hashlib
import logging
import secrets
from collections.abc import Awaitable, Callable
from typing import Any, Literal

import anyio
from pydantic import BaseModel, ConfigDict

from arzi.agents import family_explainer
from arzi.agents.family_explainer import FamilyJob
from arzi.agents.nodes import ModelSettings, ReasoningTask
from arzi.domain.enums import AppealForum, AppealStatus, ClaimMode, ReasoningStatus
from arzi.domain.models import (
    LANGUAGES,
    AppealVersion,
    AuditResult,
    ClaimFacts,
    ClaimRecord,
    FamilyAudio,
    FamilyExplanation,
    FamilyPack,
    Language,
    LlmCall,
    ShareLink,
)
from arzi.services.appeal import AppealService, SignRequest
from arzi.services.errors import (
    ClaimNotFoundError,
    ConflictError,
    InvalidStateError,
    ShareLinkInvalidError,
)
from arzi.services.ports import (
    AuditLogEntry,
    BlobStore,
    ClaimRepository,
    ConcurrentUpdateError,
    LlmUnavailableError,
    Principal,
    SpeechClient,
)

logger = logging.getLogger(__name__)

Clock = Callable[[], dt.datetime]
Reasoner = Callable[[ReasoningTask[Any], ModelSettings, list[LlmCall]], Awaitable[None]]
_CHECKED = {ReasoningStatus.PASSED, ReasoningStatus.RETRIED}


class _Out(BaseModel):
    model_config = ConfigDict(frozen=True)


class FamilyFigure(_Out):
    key: Literal["billed", "payable", "at_risk", "recoverable"]
    amount: int


class FamilyAudioOut(_Out):
    lang: Language
    seconds: float
    url: str


class FamilyAppealOut(_Out):
    forum: AppealForum
    status: AppealStatus
    version: int
    signed_by: str | None
    content_sha256: str | None


class FamilyView(_Out):
    """Everything the family page shows. No names, numbers or document text."""

    purpose: Literal["family", "public_check"]
    hospital_name: str
    hospital_city: str
    desk_contact: str
    mode: ClaimMode
    status: str
    procedure: str
    admitted_on: dt.date | None
    discharged_on: dt.date | None
    figures: list[FamilyFigure]
    explanations: list[FamilyExplanation]
    audio: list[FamilyAudioOut]
    appeal: FamilyAppealOut | None
    can_draft_appeal: bool
    expires_at: dt.datetime


class ShareCreated(_Out):
    url_path: str
    """``/f/<token>``: shown once; only the token's hash is kept."""
    share: ShareLink


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def spoken(explanation: FamilyExplanation) -> str | None:
    """The narration script: every section, rendered. None if any part failed its checks."""
    parts = [explanation.headline, *explanation.what_happened, *explanation.why]
    parts += [*explanation.next_steps, explanation.reassurance]
    texts = [p.text for p in parts]
    if explanation.status not in _CHECKED or any(t is None for t in texts):
        return None
    return " ".join(t for t in texts if t)


def figures(result: AuditResult, mode: ClaimMode) -> list[FamilyFigure]:
    t = result.totals
    shown = [
        FamilyFigure(key="billed", amount=t.billed),
        FamilyFigure(key="payable", amount=t.predicted_payable),
    ]
    if mode is ClaimMode.PRE_SUBMISSION or t.at_risk:
        shown.append(FamilyFigure(key="at_risk", amount=t.at_risk))
    if t.recoverable_on_appeal:
        shown.append(FamilyFigure(key="recoverable", amount=t.recoverable_on_appeal))
    return shown


class FamilyService:
    def __init__(
        self,
        repo: ClaimRepository,
        blobs: BlobStore,
        appeals: AppealService,
        speech: SpeechClient,
        models: ModelSettings,
        *,
        clock: Clock,
        reason: Reasoner,
        share_days: int,
        desk_contact: str,
    ) -> None:
        self._repo = repo
        self._blobs = blobs
        self._appeals = appeals
        self._speech = speech
        self._models = models
        self._clock = clock
        self._reason = reason
        self._share_days = share_days
        self._desk_contact = desk_contact

    # ------------------------------------------------------------------ desk

    async def prepare(
        self,
        principal: Principal,
        claim_id: str,
        audience: Literal["hospital", "public"] = "hospital",
    ) -> FamilyPack:
        """Explanations and audio for every language not yet prepared (cached on the claim)."""
        claim = await self._claim(principal.hospital_id, claim_id)
        facts, result = self._audited(claim)
        pack = claim.family or FamilyPack()
        done = {e.lang for e in pack.explanations if e.status in _CHECKED}
        todo = [lang for lang in LANGUAGES if lang not in done]
        if not todo and {a.lang for a in pack.audio} >= done:
            return pack

        jobs = [FamilyJob(facts=facts, audit=result, lang=lang, audience=audience) for lang in todo]
        calls: list[LlmCall] = []

        async def explain(job: FamilyJob) -> None:
            await self._reason(family_explainer.task(job), self._models, calls)

        async with anyio.create_task_group() as group:
            for job in jobs:
                group.start_soon(explain, job)
        fresh = {job.lang: job.result for job in jobs if job.result is not None}
        kept = [e for e in pack.explanations if e.lang not in fresh]
        explanations = sorted([*kept, *fresh.values()], key=lambda e: LANGUAGES.index(e.lang))

        have_audio = {a.lang: a for a in pack.audio}
        audio: list[FamilyAudio] = [a for lang, a in have_audio.items() if lang not in fresh]

        async def narrate(explanation: FamilyExplanation) -> None:
            script = spoken(explanation)
            if script is None:
                return
            try:
                narration = await self._speech.synthesize(script, explanation.lang)
            except LlmUnavailableError as exc:  # audio is optional; the text stands alone
                logger.warning("narration %s unavailable (%s)", explanation.lang, exc.slug)
                return
            digest = hashlib.sha256(script.encode()).hexdigest()
            uri = await self._blobs.put(
                principal.hospital_id,
                claim_id,
                f"family-audio-{explanation.lang}-{digest[:8]}",
                narration.audio,
                narration.content_type,
            )
            audio.append(
                FamilyAudio(
                    lang=explanation.lang,
                    uri=uri,
                    content_type=narration.content_type,
                    seconds=narration.seconds,
                    model=narration.model,
                    adapter=narration.adapter,
                    text_sha256=digest,
                )
            )

        async with anyio.create_task_group() as group:
            for explanation in explanations:
                if explanation.lang not in have_audio or explanation.lang in fresh:
                    group.start_soon(narrate, explanation)
        audio.sort(key=lambda a: LANGUAGES.index(a.lang))
        pack = FamilyPack(
            explanations=tuple(explanations), audio=tuple(audio), generated_at=self._clock()
        )
        await self._save(claim.model_copy(update={"family": pack, "updated_at": self._clock()}))
        await self._log(
            principal,
            claim_id,
            "family.prepared",
            languages=",".join(fresh),
            audio=len(audio),
            model_calls=len(calls),
        )
        return pack

    async def share(
        self,
        principal: Principal,
        claim_id: str,
        purpose: Literal["family", "public_check"] = "family",
    ) -> ShareCreated:
        claim = await self._claim(principal.hospital_id, claim_id)
        if purpose == "family":
            self._audited(claim)
            await self.prepare(principal, claim_id)
        token = secrets.token_urlsafe(32)
        now = self._clock()
        share = ShareLink(
            token_sha256=token_hash(token),
            hospital_id=principal.hospital_id,
            claim_id=claim_id,
            purpose=purpose,
            created_by=principal.user_id,
            created_at=now,
            expires_at=now + dt.timedelta(days=self._share_days),
        )
        await self._repo.save_share(share)
        await self._log(
            principal, claim_id, "family.shared", link=share.token_sha256[:12], purpose=purpose
        )
        return ShareCreated(url_path=f"/f/{token}", share=share)

    async def shares(self, principal: Principal, claim_id: str) -> list[ShareLink]:
        await self._claim(principal.hospital_id, claim_id)
        return await self._repo.list_shares(principal.hospital_id, claim_id)

    async def revoke(self, principal: Principal, claim_id: str, token_sha256: str) -> ShareLink:
        share = await self._repo.get_share(token_sha256)
        if share is None or (share.hospital_id, share.claim_id) != (
            principal.hospital_id,
            claim_id,
        ):
            raise ShareLinkInvalidError
        revoked = share.model_copy(update={"revoked_at": share.revoked_at or self._clock()})
        await self._repo.save_share(revoked)
        await self._log(principal, claim_id, "family.link_revoked", link=token_sha256[:12])
        return revoked

    # ------------------------------------------------------------------ family (by token)

    async def resolve(self, token: str) -> tuple[ShareLink, ClaimRecord, Principal]:
        """The link's claim, or one uniform 404 for unknown, expired and withdrawn links."""
        share = await self._repo.get_share(token_hash(token))
        if share is None or not share.active(self._clock()):
            raise ShareLinkInvalidError
        claim = await self._repo.get_claim(share.hospital_id, share.claim_id)
        if claim is None:
            raise ShareLinkInvalidError
        principal = Principal(
            user_id=f"link-{share.token_sha256[:8]}",
            display_name="Family link",
            hospital_id=share.hospital_id,
            role="billing_executive",
        )
        return share, claim, principal

    async def view(self, token: str) -> FamilyView:
        share, claim, _ = await self.resolve(token)
        hospital = await self._repo.get_hospital(share.hospital_id)
        facts, audit = claim.facts, claim.audit
        pack = claim.family or FamilyPack()
        appeals = await self._repo.list_appeals(share.hospital_id, share.claim_id)
        latest = appeals[-1] if appeals else None
        disputes = audit is not None and any(
            f.kind == "dispute" and f.appealable for f in audit.flags
        )
        return FamilyView(
            purpose=share.purpose,
            hospital_name=hospital.name if hospital else "",
            hospital_city=hospital.city if hospital else "",
            desk_contact=self._desk_contact if share.purpose == "family" else "",
            mode=claim.mode,
            status=str(claim.status),
            procedure=facts.admission.procedure if facts else "",
            admitted_on=facts.admission.date_in if facts else None,
            discharged_on=facts.admission.date_out if facts else None,
            figures=figures(audit, claim.mode) if audit else [],
            explanations=[e for e in pack.explanations if e.status in _CHECKED],
            audio=[
                FamilyAudioOut(
                    lang=a.lang, seconds=a.seconds, url=f"/api/v1/family/{token}/audio/{a.lang}"
                )
                for a in pack.audio
            ],
            appeal=self._appeal_out(latest),
            can_draft_appeal=share.purpose == "public_check" and disputes and latest is None,
            expires_at=share.expires_at,
        )

    async def prepare_by_token(self, token: str) -> FamilyView:
        share, claim, principal = await self.resolve(token)
        if claim.audit is None:
            raise InvalidStateError("The check is still running.")
        audience: Literal["hospital", "public"] = (
            "public" if share.purpose == "public_check" else "hospital"
        )
        await self.prepare(principal, claim.claim_id, audience)
        return await self.view(token)

    async def audio(self, token: str, lang: str) -> tuple[bytes, str]:
        _, claim, _ = await self.resolve(token)
        found = next((a for a in (claim.family or FamilyPack()).audio if a.lang == lang), None)
        if found is None:
            raise ShareLinkInvalidError("No narration in this language.")
        return await self._blobs.get(found.uri), found.content_type

    # ------------------------------------------------------------------ public check appeal

    async def draft_public_appeal(self, token: str) -> AppealVersion:
        share, claim, principal = await self.resolve(token)
        if share.purpose != "public_check":
            raise ShareLinkInvalidError
        existing = await self._repo.list_appeals(share.hospital_id, claim.claim_id)
        if existing:
            return existing[-1]
        return await self._appeals.draft(
            principal,
            claim.claim_id,
            AppealForum.INSURER_GRO,
            None,
            f"public-{share.token_sha256[:16]}",
        )

    async def sign_public_appeal(self, token: str, name: str) -> AppealVersion:
        """The policyholder (or their family) is the person who reviews and signs a public check."""
        share, claim, principal = await self.resolve(token)
        if share.purpose != "public_check":
            raise ShareLinkInvalidError
        appeals = await self._repo.list_appeals(share.hospital_id, claim.claim_id)
        if not appeals:
            raise InvalidStateError("Draft the appeal first.")
        appeal = appeals[-1]
        if appeal.status is AppealStatus.DRAFT:
            appeal = await self._appeals.submit(principal, claim.claim_id, appeal.version)
        if appeal.status is AppealStatus.IN_REVIEW:
            request = SignRequest(
                reviewer_name=name, reviewer_role="Policyholder or family member", declaration=True
            )
            appeal = await self._appeals.sign(principal, claim.claim_id, appeal.version, request)
        return appeal

    async def export_public_appeal(self, token: str) -> tuple[bytes, AppealVersion]:
        share, claim, principal = await self.resolve(token)
        if share.purpose != "public_check":
            raise ShareLinkInvalidError
        appeals = await self._repo.list_appeals(share.hospital_id, claim.claim_id)
        if not appeals:
            raise InvalidStateError("Draft the appeal first.")
        return await self._appeals.export(principal, claim.claim_id, appeals[-1].version)

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _appeal_out(appeal: AppealVersion | None) -> FamilyAppealOut | None:
        if appeal is None:
            return None
        return FamilyAppealOut(
            forum=appeal.forum,
            status=appeal.status,
            version=appeal.version,
            signed_by=appeal.signature.reviewer_name if appeal.signature else None,
            content_sha256=appeal.signature.content_sha256 if appeal.signature else None,
        )

    async def _claim(self, hospital_id: str, claim_id: str) -> ClaimRecord:
        claim = await self._repo.get_claim(hospital_id, claim_id)
        if claim is None:
            raise ClaimNotFoundError
        return claim

    @staticmethod
    def _audited(claim: ClaimRecord) -> tuple[ClaimFacts, AuditResult]:
        if claim.facts is None or claim.audit is None:
            raise InvalidStateError("Audit the claim before sharing it with the family.")
        return claim.facts, claim.audit

    async def _save(self, claim: ClaimRecord) -> None:
        try:
            await self._repo.save_claim(claim)
        except ConcurrentUpdateError:
            raise ConflictError from None

    async def _log(
        self, principal: Principal, claim_id: str, action: str, **detail: str | int | None
    ) -> None:
        entry = AuditLogEntry(
            at=self._clock(), actor=principal.user_id, action=action, detail=dict(detail)
        )
        await self._repo.append_audit_log(principal.hospital_id, claim_id, entry)
