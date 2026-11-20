import { describe, expect, it } from 'vitest';

import type { RunEvent } from '@/api/types';
import { type RunStream, runStreamReducer } from '@/api/useRunEvents';
import { stageViews } from '@/components/PipelineProgress';

const at = (s: number) => new Date(Date.UTC(2026, 10, 20, 9, 0, s)).toISOString();
const ev = (seq: number, type: RunEvent['type'], stage: string | null, data = {}): RunEvent => ({
  seq,
  type,
  stage,
  at: at(seq),
  data,
});

function play(
  events: RunEvent[],
  start: RunStream = { events: [], state: 'connecting', error: null },
) {
  return events.reduce((s, event) => runStreamReducer(s, { type: 'event', event }), start);
}

describe('run stream (SSE with Last-Event-ID resume)', () => {
  it('ignores events already seen after a reconnect, and keeps them in order', () => {
    const first = play([ev(1, 'stage.started', 'extract'), ev(2, 'stage.completed', 'extract')]);
    const dropped = runStreamReducer(first, { type: 'drop' });
    expect(dropped.state).toBe('reconnecting');
    const resumed = play(
      [
        ev(2, 'stage.completed', 'extract'),
        ev(4, 'stage.completed', 'redact'),
        ev(3, 'stage.started', 'redact'),
      ],
      runStreamReducer(dropped, { type: 'open' }),
    );
    expect(resumed.events.map((e) => e.seq)).toEqual([1, 2, 3, 4]);
    expect(resumed.state).toBe('live');
  });

  it('ends on run.completed and stays ended through later drops', () => {
    const done = play([ev(1, 'stage.started', 'extract'), ev(2, 'run.completed', null)]);
    expect(done.state).toBe('completed');
    expect(runStreamReducer(done, { type: 'drop' }).state).toBe('completed');
    expect(runStreamReducer(done, { type: 'open' }).state).toBe('completed');
  });

  it('carries the failure slug, never a message', () => {
    const failed = play([ev(1, 'run.failed', null, { error: 'replay-miss' })]);
    expect(failed).toMatchObject({ state: 'failed', error: 'replay-miss' });
  });
});

describe('pipeline stages', () => {
  it('derives each stage’s state, duration and result line', () => {
    const views = stageViews(
      [
        ev(1, 'stage.started', 'extract'),
        ev(4, 'stage.completed', 'extract', { documents: 6, model_calls: 6 }),
        ev(5, 'stage.started', 'redact'),
      ],
      false,
    );
    expect(views[0]).toMatchObject({
      id: 'extract',
      state: 'done',
      seconds: 3,
      result: '6 documents, 6 model calls',
    });
    expect(views[1]).toMatchObject({ id: 'redact', state: 'active' });
    expect(views[2]).toMatchObject({ id: 'reconcile', state: 'pending' });
    expect(stageViews([ev(1, 'stage.started', 'extract')], true)[0]?.state).toBe('failed');
  });

  it('says when an AI step was unavailable instead of pretending it ran', () => {
    const views = stageViews(
      [
        ev(1, 'stage.started', 'interpret_policy'),
        ev(2, 'stage.completed', 'interpret_policy', { status: 'unavailable' }),
      ],
      false,
    );
    expect(views.find((v) => v.id === 'interpret_policy')?.result).toBe(
      'Skipped: model unavailable',
    );
  });
});
