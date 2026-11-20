"""FamilyExplainer: the claim, explained to the patient's family in Gujarati, Hindi or English.

Same discipline as every agent: the engine decides what happened and for how much; the model
explains it in the spoken register of each language, with money only as placeholders (the
amount guard covers Gujarati and Hindi script and digits) and refs only from the whitelist.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from arzi.agents.guardrails import (
    ProsePolicy,
    Violation,
    allowed_refs,
    check_prose,
    placeholder_values,
    try_render,
    validate_citations,
)
from arzi.agents.inputs import claim_context, flag_entry, references
from arzi.agents.nodes import ReasoningTask
from arzi.agents.schemas import FamilyExplanationDraft
from arzi.domain.enums import ReasoningStatus
from arzi.domain.models import AuditResult, ClaimFacts, FamilyExplanation, Language, Prose
from arzi.prompts import load_prompt
from arzi.services.pipeline import Summary

PROMPT = load_prompt("family_explain", 2)
HUMAN_REVIEW: dict[Language, str] = {
    "en": "A qualified person at the hospital checks and signs every appeal.",
    "hi": "अस्पताल में एक योग्य व्यक्ति हर अपील की जाँच करके उस पर हस्ताक्षर करता है।",
    "gu": "હોસ્પિટલમાં એક જાણકાર વ્યક્તિ દરેક અપીલ તપાસીને તેના પર સહી કરે છે.",
}
SELF_REVIEW: dict[Language, str] = {
    "en": "You read and sign the appeal yourself before it is sent.",
    "hi": "अपील भेजने से पहले आप उसे खुद पढ़कर उस पर हस्ताक्षर करते हैं।",
    "gu": "અપીલ મોકલતા પહેલાં તમે જાતે વાંચીને તેના પર સહી કરો છો.",
}
GLOSSARY: dict[Language, dict[str, str]] = {
    "en": {
        "proportionate deduction": "a cut because the room was above the policy's room limit",
        "non-payable items": "items the policy does not pay for, such as laundry",
        "co-payment": "the share of the bill the policy asks you to pay",
        "pre-existing disease waiting period": (
            "the waiting time before an illness you had earlier is covered"
        ),
        "appeal": "a written request to the insurer to change its decision",
        "grievance officer": "the insurer's complaints officer",
    },
    "hi": {
        "proportionate deduction": "कमरे के किराए की सीमा से ऊपर होने के कारण कटौती",
        "non-payable items": "वे चीज़ें जिनका भुगतान पॉलिसी नहीं करती, जैसे कपड़े धुलाई",
        "co-payment": "बिल का वह हिस्सा जो पॉलिसी के अनुसार आपको देना है",
        "pre-existing disease waiting period": "पहले से मौजूद बीमारी के कवर होने से पहले का इंतज़ार",
        "appeal": "बीमा कंपनी से फ़ैसला बदलने की लिखित माँग",
        "grievance officer": "बीमा कंपनी के शिकायत अधिकारी",
        "insurer": "बीमा कंपनी",
    },
    "gu": {
        "proportionate deduction": "રૂમના ભાડાની મર્યાદા કરતાં વધુ હોવાથી કરેલો કાપ",
        "non-payable items": "એવી વસ્તુઓ જેના પૈસા પોલિસી નથી ચૂકવતી, જેમ કે કપડાં ધોવાના",
        "co-payment": "બિલનો એ ભાગ જે પોલિસી પ્રમાણે તમારે ભરવાનો છે",
        "pre-existing disease waiting period": (
            "પહેલેથી હોય એવી બીમારી કવર થાય તે પહેલાંનો રાહ જોવાનો સમય"
        ),
        "appeal": "વીમા કંપનીને નિર્ણય બદલવા માટેની લેખિત અરજી",
        "grievance officer": "વીમા કંપનીના ફરિયાદ અધિકારી",
        "insurer": "વીમા કંપની",
    },
}


# Words that promise an outcome nobody can guarantee ("surely", "will be paid back").
# Hindi ज़रूर only as a whole word (ज़रूरत is "need"); Gujarati જરૂર is left out because it
# also means "needed", and ચોક્કસ only before change/get/back (it also means "specific").
PROMISE = re.compile(
    r"\b(?:surely|definitely|guaranteed?"
    r"|will (?:be )?(?:reversed|refunded|paid back|approved|win))\b"
    r"|(?:ज़रूर|जरूर)(?![\u0900-\u097f])|पक्का|निश्चित रूप से"
    r"|ચોક્કસ(?:પણે)? (?:બદલ|મળ|પાછ)|ખાતરીપૂર્વક",
    re.IGNORECASE,
)


@dataclass
class FamilyJob:
    facts: ClaimFacts
    audit: AuditResult
    lang: Language
    audience: Literal["hospital", "public"] = "hospital"
    """Who signs the appeal: a qualified person at the hospital, or the family themselves (free
    check). Only the fixed closing note differs; it is not sent to the model."""
    result: FamilyExplanation | None = None
    violations: tuple[Violation, ...] = field(default_factory=tuple)

    def prose_policy(self) -> ProsePolicy:
        refs = allowed_refs(self.facts, (r for f in self.audit.flags for r in f.citation_refs))
        return ProsePolicy(refs, frozenset(placeholder_values(self.facts, self.audit)))


def task(job: FamilyJob) -> ReasoningTask[FamilyExplanationDraft]:
    def build() -> dict[str, Any] | None:
        policy = job.prose_policy()
        return {
            "lang": job.lang,
            "claim": claim_context(job.facts),
            "flags": [flag_entry(flag, job.facts) for flag in job.audit.flags],
            "glossary": GLOSSARY[job.lang],
            "references": references(policy.allowed_refs, job.facts),
            "allowed_refs": sorted(policy.allowed_refs),
            "placeholders": sorted(policy.placeholders),
        }

    def check(output: FamilyExplanationDraft) -> Sequence[Violation]:
        policy = job.prose_policy()
        found = validate_citations(output.citations, policy.allowed_refs, "citations")
        sections = [("headline", output.headline), ("reassurance", output.reassurance)]
        for name in ("what_happened", "why", "next_steps"):
            sections += [(f"{name}[{i}]", text) for i, text in enumerate(getattr(output, name))]
        for where, text in sections:
            found += check_prose(text, policy, where)
            if PROMISE.search(text):
                found.append(Violation("outcome_promise", where))
        return found

    def finish(
        output: FamilyExplanationDraft | None,
        status: ReasoningStatus,
        violations: Sequence[Violation],
    ) -> Summary:
        values = placeholder_values(job.facts, job.audit)

        def prose(template: str) -> Prose:
            return Prose(template=template, text=try_render(template, values))

        draft = output or FamilyExplanationDraft(
            headline="", what_happened=[], why=[], next_steps=[], reassurance="", citations=[]
        )
        reassurance = draft.reassurance.strip()
        note = (HUMAN_REVIEW if job.audience == "hospital" else SELF_REVIEW)[job.lang]
        if note not in reassurance:
            # The review note is fixed wording, so it is always present and always exact.
            reassurance = f"{reassurance} {note}".strip()
        job.violations = tuple(violations)
        job.result = FamilyExplanation(
            lang=job.lang,
            status=status,
            prompt_ref=PROMPT.ref,
            violations=tuple(str(v) for v in violations),
            headline=prose(draft.headline),
            what_happened=tuple(prose(s) for s in draft.what_happened),
            why=tuple(prose(s) for s in draft.why),
            next_steps=tuple(prose(s) for s in draft.next_steps),
            reassurance=prose(reassurance),
        )
        return {"status": str(status), "lang": job.lang}

    return ReasoningTask(
        name=f"family_explain_{job.lang}",
        prompt=PROMPT,
        schema=FamilyExplanationDraft,
        build_input=build,
        check=check,
        finish=finish,
        max_output_tokens=8192,
    )
