/** What happened to this claim: the audit log, and each run's stages, models, tokens and cost. */
import { Cpu, History } from 'lucide-react';

import { useAuditLog, useRuns } from '@/api/queries';
import type { AuditRun } from '@/api/types';
import { ProblemAlert } from '@/components/states';
import { Badge, Card, CardHeader, CardTitle, Skeleton } from '@/components/ui/primitives';
import { formatCount, formatDateTime, formatDuration, formatMicroInr } from '@/lib/format';
import { STAGE } from '@/lib/labels';

const ACTION: Record<string, string> = {
  'claim.created': 'Claim created',
  'consent.recorded': 'Consent recorded',
  'document.uploaded': 'Document uploaded',
  'run.started': 'Audit started',
  'run.completed': 'Audit completed',
  'run.failed': 'Audit failed',
  'line.corrected': 'Bill line corrected',
  'flag.accepted': 'Flag accepted',
  'flag.dismissed': 'Flag dismissed',
  'appeal.drafted': 'Appeal drafted',
  'appeal.edited': 'Appeal edited',
  'appeal.submitted': 'Appeal submitted for review',
  'appeal.signed': 'Appeal signed',
  'appeal.exported': 'Signed appeal exported',
};

function stageTimes(run: AuditRun): { stage: string; seconds: number }[] {
  const events = run.events;
  return events
    .filter((e) => e.type === 'stage.completed' && e.stage)
    .map((done) => {
      const start = events.find((e) => e.type === 'stage.started' && e.stage === done.stage);
      return {
        stage: done.stage ?? '',
        seconds: start ? (new Date(done.at).getTime() - new Date(start.at).getTime()) / 1000 : 0,
      };
    });
}

function RunCard({ run }: { run: AuditRun }) {
  const calls = run.calls;
  const tokens = calls.reduce(
    (s, c) => s + c.input_tokens + c.output_tokens + c.thinking_tokens,
    0,
  );
  const cost = calls.reduce((s, c) => s + c.cost_micro_inr, 0);
  const total = run.finished_at
    ? (new Date(run.finished_at).getTime() - new Date(run.started_at).getTime()) / 1000
    : null;
  const models = [...new Set(calls.map((c) => c.model))];
  const replayed = calls.length > 0 && calls.every((c) => c.replayed);
  return (
    <li className="px-5 py-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-xs text-ink-muted">{run.run_id}</span>
        <Badge
          tone={
            run.status === 'completed' ? 'success' : run.status === 'failed' ? 'danger' : 'info'
          }
        >
          {run.status}
        </Badge>
        {replayed ? <Badge tone="info">Replayed responses</Badge> : null}
        <span className="ml-auto text-xs text-ink-subtle">
          {formatDateTime(run.started_at)} · {formatDuration(total)}
        </span>
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-3 text-[0.8125rem] sm:grid-cols-4">
        <div>
          <dt className="text-xs text-ink-subtle">Model calls</dt>
          <dd className="font-medium tabular-nums">{calls.length}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-subtle">Tokens</dt>
          <dd className="font-medium tabular-nums">{tokens.toLocaleString('en-IN')}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-subtle">Cost of this audit</dt>
          <dd className="font-medium tabular-nums">{formatMicroInr(cost)}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-subtle">Models</dt>
          <dd className="truncate font-medium">{models.join(', ') || '—'}</dd>
        </div>
      </dl>
      <ol className="mt-3 flex flex-wrap gap-1.5">
        {stageTimes(run).map((s) => (
          <li key={s.stage}>
            <Badge>
              {STAGE[s.stage]?.label ?? s.stage} · {formatDuration(s.seconds)}
            </Badge>
          </li>
        ))}
      </ol>
      {run.prompt_versions.length ? (
        <p className="mt-2 text-xs text-ink-subtle">
          Prompts: <span className="font-mono">{run.prompt_versions.join(' · ')}</span>
        </p>
      ) : null}
    </li>
  );
}

export function ActivityTab({ claimId }: { claimId: string }) {
  const runs = useRuns(claimId);
  const log = useAuditLog(claimId);
  return (
    <div className="space-y-4 p-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Cpu className="size-4 text-accent" aria-hidden /> Audit runs
          </CardTitle>
        </CardHeader>
        {runs.isError ? (
          <ProblemAlert error={runs.error} onRetry={() => void runs.refetch()} className="m-4" />
        ) : runs.isPending ? (
          <Skeleton className="m-4 h-24" />
        ) : (
          <ul className="divide-y divide-border">
            {runs.data.map((run) => (
              <RunCard key={run.run_id} run={run} />
            ))}
          </ul>
        )}
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <History className="size-4 text-accent" aria-hidden /> Audit log
          </CardTitle>
          <span className="text-xs text-ink-subtle">
            {log.data ? formatCount(log.data.length, 'entry', 'entries') : null} · append-only
          </span>
        </CardHeader>
        {log.isError ? (
          <ProblemAlert error={log.error} onRetry={() => void log.refetch()} className="m-4" />
        ) : log.isPending ? (
          <Skeleton className="m-4 h-40" />
        ) : (
          <ol className="relative space-y-0 px-5 py-3">
            {[...log.data].reverse().map((entry, i) => (
              <li
                key={`${entry.at}-${String(i)}`}
                className="relative border-l border-border py-2 pl-5"
              >
                <span
                  className="absolute top-3.5 -left-1 size-2 rounded-full bg-navy"
                  aria-hidden
                />
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span className="font-medium">{ACTION[entry.action] ?? entry.action}</span>
                  <span className="text-xs text-ink-subtle">
                    {formatDateTime(entry.at)} · {entry.actor}
                  </span>
                </div>
                {Object.keys(entry.detail ?? {}).length ? (
                  <p className="mt-0.5 font-mono text-xs text-ink-subtle">
                    {Object.entries(entry.detail ?? {})
                      .filter(([, v]) => v !== null)
                      .map(([k, v]) => `${k}=${String(v)}`)
                      .join('  ')}
                  </p>
                ) : null}
              </li>
            ))}
          </ol>
        )}
      </Card>
    </div>
  );
}
