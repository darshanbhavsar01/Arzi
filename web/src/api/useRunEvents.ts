/**
 * Live audit progress over SSE. The server numbers every event, so after a dropped connection
 * the browser's EventSource reconnects with `Last-Event-ID` and resumes where it stopped; events
 * already seen are ignored by `seq`. The stream is closed on `run.completed` / `run.failed`,
 * otherwise EventSource would keep reconnecting to a finished run.
 */
import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useReducer } from 'react';

import { keys } from '@/api/queries';
import type { RunEvent } from '@/api/types';

export type StreamState = 'idle' | 'connecting' | 'live' | 'reconnecting' | 'completed' | 'failed';

export interface RunStream {
  events: RunEvent[];
  state: StreamState;
  error: string | null;
}

const EVENT_TYPES = [
  'stage.started',
  'stage.completed',
  'flag.created',
  'run.completed',
  'run.failed',
] as const;

type Action =
  { type: 'reset' } | { type: 'open' } | { type: 'drop' } | { type: 'event'; event: RunEvent };

const initial: RunStream = { events: [], state: 'idle', error: null };

export function runStreamReducer(stream: RunStream, action: Action): RunStream {
  switch (action.type) {
    case 'reset':
      return { events: [], state: 'connecting', error: null };
    case 'open':
      return stream.state === 'completed' || stream.state === 'failed'
        ? stream
        : { ...stream, state: 'live' };
    case 'drop':
      return stream.state === 'completed' || stream.state === 'failed'
        ? stream
        : { ...stream, state: 'reconnecting' };
    case 'event': {
      const { event } = action;
      if (stream.events.some((e) => e.seq === event.seq)) return stream;
      const events = [...stream.events, event].sort((a, b) => a.seq - b.seq);
      if (event.type === 'run.completed') return { events, state: 'completed', error: null };
      if (event.type === 'run.failed') {
        const slug = event.data?.error;
        return { events, state: 'failed', error: typeof slug === 'string' ? slug : 'run-failed' };
      }
      return { ...stream, events };
    }
  }
}

export function useRunEvents(claimId: string, runId: string | null): RunStream {
  const [stream, dispatch] = useReducer(runStreamReducer, initial);
  const client = useQueryClient();

  useEffect(() => {
    if (!runId) return;
    dispatch({ type: 'reset' });
    const source = new EventSource(`/api/v1/claims/${claimId}/runs/${runId}/events`);
    source.onopen = () => {
      dispatch({ type: 'open' });
    };
    source.onerror = () => {
      dispatch({ type: 'drop' });
    };
    const onEvent = (message: MessageEvent<string>) => {
      // `seq` and `type` travel as the SSE id and event name, the rest as JSON data.
      const body = JSON.parse(message.data) as Omit<RunEvent, 'seq' | 'type'>;
      const event = {
        ...body,
        seq: Number(message.lastEventId),
        type: message.type as RunEvent['type'],
      } satisfies RunEvent;
      dispatch({ type: 'event', event });
      if (event.type === 'run.completed' || event.type === 'run.failed') {
        source.close();
        void client.invalidateQueries({ queryKey: keys.claim(claimId) });
        void client.invalidateQueries({ queryKey: keys.documents(claimId) });
        void client.invalidateQueries({ queryKey: keys.runs(claimId) });
        void client.invalidateQueries({ queryKey: keys.log(claimId) });
        void client.invalidateQueries({ queryKey: keys.allClaims });
      }
    };
    for (const type of EVENT_TYPES) source.addEventListener(type, onEvent);
    return () => {
      source.close();
    };
  }, [claimId, runId, client]);

  return stream;
}
