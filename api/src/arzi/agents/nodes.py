"""ADK nodes: deterministic steps and guarded reasoning steps.

Every node announces itself with ``stage.started`` / ``stage.completed`` events carried in
``Event.custom_metadata``; the pipeline maps those 1:1 onto the run's SSE contract, so the
frontend sees the same stream whether a stage is code or a model.

A reasoning node runs an ``LlmAgent`` (structured output) and then the guardrails. A failed
check is retried once with the validator's feedback appended to the input; a second failure
keeps the draft with status ``needs_review``. A model that is unavailable (outage, budget
reached, replay miss) leaves the step ``unavailable``: reasoning adds explanations, never the
money, so the deterministic audit still completes without it.
"""

import json
from collections.abc import AsyncGenerator, Callable, Sequence
from dataclasses import dataclass
from typing import Any

from google.adk.agents import BaseAgent, LlmAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.events import Event, EventActions
from pydantic import BaseModel, ConfigDict, ValidationError

from arzi.agents.bridge import PortModel, instruction
from arzi.agents.guardrails import Violation, feedback
from arzi.domain.enums import ReasoningStatus
from arzi.domain.models import LlmCall
from arzi.prompts import Prompt
from arzi.services.cost_ledger import BudgetExceededError, PriceUnknownError
from arzi.services.pipeline import PipelineStep, RunContext, Summary
from arzi.services.ports import LlmClient, LlmUnavailableError

META_EVENT, META_STAGE, META_DATA = "arzi_event", "arzi_stage", "arzi_data"
_NO_OUTPUT = (LlmUnavailableError, BudgetExceededError, PriceUnknownError, ValidationError)


def stage_event(
    ctx: InvocationContext, author: str, kind: str, data: Summary | None = None
) -> Event:
    return Event(
        author=author,
        invocation_id=ctx.invocation_id,
        custom_metadata={META_EVENT: kind, META_STAGE: author, META_DATA: dict(data or {})},
    )


class StepNode(BaseAgent):
    """A deterministic pipeline step (extraction calls, redaction, reconcile, rules engine)."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    step: Any  # PipelineStep
    run_context: RunContext

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        step: PipelineStep = self.step
        yield stage_event(ctx, self.name, "stage.started")
        summary = await step.run(self.run_context)
        yield stage_event(ctx, self.name, "stage.completed", summary)


@dataclass(frozen=True)
class ReasoningTask[T: BaseModel]:
    """One model-written step: its prompt and schema, how to build its input from what earlier
    steps produced, the guardrail check, and what to do with the outcome."""

    name: str
    prompt: Prompt
    schema: type[T]
    build_input: Callable[[], dict[str, Any] | None]
    """None skips the step (nothing to explain, no policy to read)."""
    check: Callable[[T], Sequence[Violation]]
    finish: Callable[[T | None, ReasoningStatus, Sequence[Violation]], Summary]
    max_output_tokens: int = 4096


@dataclass(frozen=True)
class ModelSettings:
    client: LlmClient
    model: str
    thinking_budget: int = -1


def reasoning_node(
    task: ReasoningTask[Any], models: ModelSettings, calls: list[LlmCall]
) -> "ReasoningNode":
    input_key, output_key = f"{task.name}_input", f"{task.name}_output"

    def provide(context: ReadonlyContext) -> str:
        return instruction(task.prompt, str(context.state.get(input_key, "")))

    agent = LlmAgent(
        name=f"{task.name}_model",
        model=PortModel(
            model=models.model,
            client=models.client,
            prompt=task.prompt,
            output=task.schema,
            record=calls.append,
            max_output_tokens=task.max_output_tokens,
            thinking_budget=models.thinking_budget,
        ),
        instruction=provide,
        output_schema=task.schema,
        output_key=output_key,
        include_contents="none",
    )
    return ReasoningNode(name=task.name, task=task, agent=agent, sub_agents=[agent])


class ReasoningNode(BaseAgent):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    task: Any  # ReasoningTask
    agent: LlmAgent

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        task: ReasoningTask[Any] = self.task
        yield stage_event(ctx, self.name, "stage.started")
        payload = task.build_input()
        if payload is None:
            summary = task.finish(None, ReasoningStatus.SKIPPED, ())
            yield stage_event(ctx, self.name, "stage.completed", summary)
            return
        base = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=1)
        output: BaseModel | None = None
        violations: Sequence[Violation] = ()
        status = ReasoningStatus.UNAVAILABLE
        for attempt in range(2):
            text = base if attempt == 0 else f"{base}\n\n{feedback(violations)}"
            yield Event(
                author=self.name,
                invocation_id=ctx.invocation_id,
                actions=EventActions(state_delta={f"{task.name}_input": text}),
            )
            try:
                async for event in self.agent.run_async(ctx):
                    yield event
                output = task.schema.model_validate(ctx.session.state.get(f"{task.name}_output"))
            except _NO_OUTPUT:
                output, status = None, ReasoningStatus.UNAVAILABLE
                break
            violations = tuple(task.check(output))
            if not violations:
                status = ReasoningStatus.PASSED if attempt == 0 else ReasoningStatus.RETRIED
                break
            status = ReasoningStatus.NEEDS_REVIEW
        summary = task.finish(output, status, violations)
        yield stage_event(ctx, self.name, "stage.completed", summary)
