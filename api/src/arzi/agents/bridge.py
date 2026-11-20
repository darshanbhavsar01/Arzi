"""An ADK model that routes ``LlmAgent`` calls through Arzi's ``LlmClient`` port.

ADK would otherwise call Gemini itself. Going through the port keeps one path for every model
call: ``live`` (Vertex AI behind the budget guard, with the timeout and retry policy), ``replay``
(recorded responses) and ``fake`` (deterministic stubs), with token usage on the run's cost
ledger and the prompt version recorded with every output.

The agent's instruction is the versioned prompt followed by this run's input between
``<arzi-input>`` markers. ADK may append its own lines to the instruction; only the prompt and
the marked input are sent, so recordings stay keyed by prompt version and input alone.
"""

import re
from collections.abc import AsyncGenerator, Callable
from typing import Any

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest as AdkRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from pydantic import BaseModel, ConfigDict

from arzi.domain.models import LlmCall
from arzi.prompts import Prompt
from arzi.services.ports import LlmClient, LlmRequest

INPUT_OPEN, INPUT_CLOSE = "<arzi-input>", "</arzi-input>"
_INPUT = re.compile(re.escape(INPUT_OPEN) + r"\n(.*)\n" + re.escape(INPUT_CLOSE), re.DOTALL)


def instruction(prompt: Prompt, payload: str) -> str:
    return f"{prompt.text}\n\n{INPUT_OPEN}\n{payload}\n{INPUT_CLOSE}"


def extract_input(text: str) -> str:
    match = _INPUT.search(text)
    if match is None:
        raise ValueError("instruction has no arzi input block")
    return match.group(1)


class PortModel(BaseLlm):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    model: str
    client: Any  # LlmClient; a Protocol, so pydantic cannot validate it
    prompt: Prompt
    output: type[BaseModel]
    record: Callable[[LlmCall], None]
    """Receives each call's usage for the run record (a callable: pydantic would copy a list)."""
    max_output_tokens: int = 4096
    temperature: float = 0.2
    thinking_budget: int = -1
    """-1 leaves thinking at the model's default (``ARZI_REASONING_THINKING_BUDGET``)."""

    async def generate_content_async(
        self, llm_request: AdkRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        config = llm_request.config
        system = config.system_instruction if config else None
        client: LlmClient = self.client
        result = await client.generate_structured(
            LlmRequest(
                prompt_ref=self.prompt.ref,
                system=self.prompt.text,
                schema=self.output,
                model=self.model,
                text=extract_input(str(system or "")),
                max_output_tokens=self.max_output_tokens,
                temperature=self.temperature,
                thinking_budget=self.thinking_budget,
            )
        )
        call = result.call
        self.record(call)
        yield LlmResponse(
            content=types.Content(
                role="model", parts=[types.Part(text=result.output.model_dump_json())]
            ),
            usage_metadata=types.GenerateContentResponseUsageMetadata(
                prompt_token_count=call.input_tokens,
                candidates_token_count=call.output_tokens,
                thoughts_token_count=call.thinking_tokens,
            ),
        )
