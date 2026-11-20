"""Per-document classification and structured extraction with Gemini.

A document whose type the uploader already chose skips classification. Reports and implant
invoices only need to be identified (their presence satisfies the claim-documents check), so
they cost one cheap call or none. Documents are processed concurrently, a few at a time.
"""

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field

import anyio
from pydantic import BaseModel

from arzi.domain.models import LlmCall
from arzi.prompts import Prompt, load_prompt
from arzi.services.extraction_schemas import EXTRACTION_SCHEMAS, Classification, DocType
from arzi.services.ports import FilePart, LlmClient, LlmRequest, StoredDocument

CLASSIFY = load_prompt("classify_document", 1)
PROMPTS: dict[DocType, Prompt] = {
    DocType.POLICY_SCHEDULE: load_prompt("extract_policy", 2),
    DocType.POLICY_WORDING: load_prompt("extract_policy", 2),
    DocType.ITEMISED_BILL: load_prompt("extract_bill", 1),
    DocType.DISCHARGE_SUMMARY: load_prompt("extract_discharge", 1),
    DocType.INSURER_LETTER: load_prompt("extract_insurer_letter", 1),
}


@dataclass
class DocumentExtraction:
    document: StoredDocument
    document_type: DocType
    extraction: BaseModel | None
    calls: list[LlmCall] = field(default_factory=list)


Loader = Callable[[StoredDocument], Awaitable[bytes]]


class ExtractionService:
    def __init__(
        self, llm: LlmClient, *, model: str, thinking_budget: int = 0, concurrency: int = 3
    ) -> None:
        self._llm = llm
        self._model = model
        self._thinking_budget = thinking_budget
        self._concurrency = concurrency

    async def extract_one(self, document: StoredDocument, data: bytes) -> DocumentExtraction:
        part = FilePart(
            data=data, mime_type=document.content_type, sha256=document.sha256, uri=document.uri
        )
        calls: list[LlmCall] = []
        doc_type = document.document_type
        if doc_type is None:
            classified = await self._llm.generate_structured(
                self._request(CLASSIFY, Classification, part, max_output_tokens=256)
            )
            calls.append(classified.call)
            doc_type = classified.output.document_type
        schema = EXTRACTION_SCHEMAS.get(doc_type)
        if schema is None:
            return DocumentExtraction(document, doc_type, None, calls)
        result = await self._llm.generate_structured(self._request(PROMPTS[doc_type], schema, part))
        calls.append(result.call)
        return DocumentExtraction(document, doc_type, result.output, calls)

    async def extract_all(
        self, documents: Sequence[StoredDocument], load: Loader
    ) -> list[DocumentExtraction]:
        """All documents, in upload order, at most ``concurrency`` model calls in flight."""
        results: list[DocumentExtraction | None] = [None] * len(documents)
        limiter = anyio.Semaphore(self._concurrency)

        async def run(index: int, document: StoredDocument) -> None:
            async with limiter:
                results[index] = await self.extract_one(document, await load(document))

        async with anyio.create_task_group() as group:
            for index, document in enumerate(documents):
                group.start_soon(run, index, document)
        return [r for r in results if r is not None]

    def _request[T: BaseModel](
        self, prompt: Prompt, schema: type[T], part: FilePart, *, max_output_tokens: int = 8192
    ) -> LlmRequest[T]:
        return LlmRequest(
            prompt_ref=prompt.ref,
            system=prompt.text,
            schema=schema,
            model=self._model,
            files=(part,),
            max_output_tokens=max_output_tokens,
            temperature=0.0,
            thinking_budget=self._thinking_budget,
        )
