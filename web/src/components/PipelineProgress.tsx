/**
 * The audit as it happens, from the run's SSE events: each stage with its state, duration and a
 * one-line result. Screen readers hear the current stage through a polite live region.
 */
import { Check, CircleAlert, Loader2 } from 'lucide-react';

import type { RunEvent } from '@/api/types';
import type { StreamState } from '@/api/useRunEvents';
import { cn } from '@/lib/cn';
import { formatDuration, formatMoney } from '@/lib/format';
import { STAGE } from '@/lib/labels';

export const STAGES = [
  'extract',
  'redact',
  'reconcile',
  'interpret_policy',
  'audit',
  'explain_flags',
] as const;

type StageState = 'pending' | 'active' | 'done' | 'failed';

interface StageView {
  id: string;
  state: StageState;
  seconds: number | null;
  result: string | null;
}

type Data = Record<string, string | number | boolean | null>;

function resultLine(stage: string, data: Data): string | null {
  const n = (key: string) => (typeof data[key] === 'number' ? data[key] : 0);
  switch (stage) {
    case 'extract':
      return `${String(n('documents'))} documents, ${String(n('model_calls'))} model calls`;
    case 'redact':
      return `${String(n('identifiers_removed'))} identifiers removed`;
    case 'reconcile':
      return `${String(n('bill_lines'))} bill lines${n('needs_confirmation') ? ` · ${String(n('needs_confirmation'))} to confirm` : ''}`;
    case 'interpret_policy':
      return data.status === 'unavailable'
        ? 'Skipped: model unavailable'
        : `${String(n('terms'))} terms mapped`;
    case 'audit':
      return `${String(n('flags'))} flags · ${formatMoney(n('at_risk'))} at risk`;
    case 'explain_flags':
      return data.status === 'unavailable'
        ? 'Skipped: model unavailable'
        : `${String(n('explained'))} explained`;
    default:
      return null;
  }
}

export function stageViews(events: RunEvent[], failed: boolean): StageView[] {
  return STAGES.map((id) => {
    const started = events.find((e) => e.type === 'stage.started' && e.stage === id);
    const done = events.find((e) => e.type === 'stage.completed' && e.stage === id);
    const seconds =
      started && done
        ? (new Date(done.at).getTime() - new Date(started.at).getTime()) / 1000
        : null;
    const state: StageState = done ? 'done' : started ? (failed ? 'failed' : 'active') : 'pending';
    return { id, state, seconds, result: done ? resultLine(id, done.data ?? {}) : null };
  });
}

export function PipelineProgress({
  events,
  state,
  className,
}: {
  events: RunEvent[];
  state: StreamState;
  className?: string;
}) {
  const views = stageViews(events, state === 'failed');
  const current = views.find((v) => v.state === 'active');
  const announcement =
    state === 'completed'
      ? 'Audit complete.'
      : state === 'failed'
        ? 'The audit stopped.'
        : current
          ? `${STAGE[current.id]?.label ?? current.id}…`
          : 'Starting the audit…';

  return (
    <div className={className}>
      <p className="sr-only" aria-live="polite">
        {announcement}
      </p>
      <ol className="space-y-1">
        {views.map((view) => {
          const meta = STAGE[view.id];
          return (
            <li
              key={view.id}
              className={cn(
                'flex items-start gap-3 rounded-lg px-3 py-2.5 transition-colors',
                view.state === 'active' && 'bg-navy-soft',
              )}
            >
              <span
                className={cn(
                  'mt-0.5 grid size-5 shrink-0 place-content-center rounded-full border',
                  view.state === 'done' && 'border-success bg-success text-white',
                  view.state === 'active' && 'border-navy text-navy',
                  view.state === 'failed' && 'border-danger bg-danger text-white',
                  view.state === 'pending' && 'border-border-strong text-transparent',
                )}
                aria-hidden
              >
                {view.state === 'done' ? (
                  <Check className="size-3" strokeWidth={3} />
                ) : view.state === 'active' ? (
                  <Loader2 className="size-3 animate-spin" />
                ) : view.state === 'failed' ? (
                  <CircleAlert className="size-3" />
                ) : null}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline justify-between gap-3">
                  <span
                    className={cn(
                      'font-medium',
                      view.state === 'pending' ? 'text-ink-subtle' : 'text-ink',
                    )}
                  >
                    {meta?.label ?? view.id}
                  </span>
                  <span className="text-xs tabular-nums text-ink-subtle">
                    {view.seconds !== null
                      ? formatDuration(view.seconds)
                      : view.state === 'active'
                        ? 'running'
                        : ''}
                  </span>
                </div>
                <p className="text-xs text-ink-subtle">{view.result ?? meta?.detail}</p>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
