"""The audit as an ADK ``Workflow``, and a runner for on-demand reasoning (appeal drafting).

    START → extract → redact → reconcile → interpret_policy → audit → explain_flags

Deterministic steps are custom agents wrapping the Phase 3 steps; ``interpret_policy`` and
``explain_flags`` are guarded ``LlmAgent``s. ADK runs in-process with an in-memory session per
run (ADR-0004); the run record in Firestore stays the source of truth, so nothing is lost when
the session is discarded. Node events map 1:1 onto the run's SSE events.
"""

from collections.abc import AsyncIterator, Sequence
from itertools import pairwise
from typing import Any

from google.adk.agents import BaseAgent
from google.adk.events import Event
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.workflow import START, Workflow
from google.genai import types

from arzi.agents import flag_explainer, policy_interpreter
from arzi.agents.nodes import (
    META_DATA,
    META_EVENT,
    META_STAGE,
    ModelSettings,
    ReasoningTask,
    StepNode,
    reasoning_node,
)
from arzi.domain.models import LlmCall
from arzi.services.pipeline import (
    AuditStep,
    ExtractStep,
    PipelineStep,
    ReconcileStep,
    RedactStep,
    RunContext,
    StageEvent,
    flag_events,
)

APP_NAME = "arzi"
_USER = "arzi-pipeline"


def _chain(name: str, nodes: Sequence[BaseAgent]) -> Workflow:
    edges: list[Any] = [(START, nodes[0])]
    edges += list(pairwise(nodes))
    return Workflow(name=name, edges=edges)


async def _events(root: Workflow) -> AsyncIterator[Event]:
    sessions = InMemorySessionService()
    session = await sessions.create_session(app_name=APP_NAME, user_id=_USER)
    runner = Runner(app_name=APP_NAME, node=root, session_service=sessions)
    start = types.Content(role="user", parts=[types.Part(text="run")])
    async for event in runner.run_async(user_id=_USER, session_id=session.id, new_message=start):
        yield event


def _stage(event: Event) -> StageEvent | None:
    meta = event.custom_metadata or {}
    kind = meta.get(META_EVENT)
    if kind is None:
        return None
    return StageEvent(kind, meta[META_STAGE], meta.get(META_DATA) or {})


class AdkAuditPipeline:
    def __init__(
        self,
        extract: ExtractStep,
        redact: RedactStep,
        reconcile: ReconcileStep,
        audit: AuditStep,
        models: ModelSettings,
    ) -> None:
        self._steps: tuple[PipelineStep, ...] = (extract, redact, reconcile, audit)
        self._models = models

    def workflow(self, ctx: RunContext) -> Workflow:
        """A fresh graph per run: nodes hold this run's context."""
        extract, redact, reconcile, audit = (
            StepNode(name=s.name, step=s, run_context=ctx) for s in self._steps
        )
        interpret = reasoning_node(policy_interpreter.task(ctx), self._models, ctx.calls)
        explain = reasoning_node(flag_explainer.task(ctx), self._models, ctx.calls)
        return _chain("arzi_audit", [extract, redact, reconcile, interpret, audit, explain])

    async def stream(self, ctx: RunContext) -> AsyncIterator[StageEvent]:
        async for event in _events(self.workflow(ctx)):
            stage = _stage(event)
            if stage is None:
                continue
            yield stage
            if stage.type == "stage.completed" and stage.stage == AuditStep.name:
                for flagged in flag_events(ctx):
                    yield flagged


async def run_reasoning(
    task: ReasoningTask[Any], models: ModelSettings, calls: list[LlmCall]
) -> None:
    """Run one guarded reasoning step on its own; its ``finish`` stores the outcome."""
    async for _ in _events(_chain(f"arzi_{task.name}", [reasoning_node(task, models, calls)])):
        pass
