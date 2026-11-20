"""Structured outputs of the reasoning agents (``LlmAgent(output_schema=...)``).

Kept flat and free of length constraints so Gemini's response schema accepts them; the
guardrails, not the schema, decide whether an answer is usable. Prose fields carry money only
as ``{{placeholder}}`` names from the input.
"""

from pydantic import BaseModel, ConfigDict, Field

from arzi.domain.enums import PolicyTermKind


class _Schema(BaseModel):
    model_config = ConfigDict(extra="ignore")


class PolicyTermDraft(_Schema):
    term: PolicyTermKind
    clause_id: str | None = Field(
        None, description="The governing clause ID exactly as it appears in the input, or null."
    )
    summary: str = Field(description="One or two plain sentences; amounts only as placeholders.")
    confidence: float = Field(ge=0, le=1)


class PolicyTermsDraft(_Schema):
    terms: list[PolicyTermDraft]
    citations: list[str] = Field(description="allowed_refs entries relied on, e.g. policy:4.2")


class FlagNarrativeDraft(_Schema):
    flag_id: str
    headline: str = Field(description="At most 12 words, no amounts.")
    explanation: str = Field(description="Why this was flagged; amounts only as placeholders.")
    fix: str = Field(description="What the billing desk should do next.")
    citations: list[str]


class FlagNarrativesDraft(_Schema):
    items: list[FlagNarrativeDraft]


class AppealArgumentDraft(_Schema):
    flag_id: str
    argument: str = Field(description="Why the insurer's decision on this item is wrong.")
    citations: list[str]


class AppealDraftOutput(_Schema):
    subject: str
    facts: str = Field(description="Admission, treatment and the insurer's decision, briefly.")
    items: list[AppealArgumentDraft]
    relief: str = Field(description="The relief sought; must contain {{totals.recoverable}}.")
    citations: list[str]


class FamilyExplanationDraft(_Schema):
    headline: str = Field(description="One short sentence: what this means for the family.")
    what_happened: list[str] = Field(description="Two to four short sentences.")
    why: list[str] = Field(description="Two to four short sentences, no jargon.")
    next_steps: list[str] = Field(description="Two to four concrete steps for the family.")
    reassurance: str = Field(description="One or two sentences; ends with the human-review note.")
    citations: list[str]
