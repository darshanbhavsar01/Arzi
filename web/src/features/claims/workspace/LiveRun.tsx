/** The audit while it runs: streamed stages on the left, flags appearing as the engine finds them. */
import { Radio, WifiOff } from 'lucide-react';

import type { RunStream } from '@/api/useRunEvents';
import { Money, SeverityDot } from '@/components/domain';
import { PipelineProgress } from '@/components/PipelineProgress';
import { Card, CardHeader, CardTitle } from '@/components/ui/primitives';
import { ruleTitle } from '@/lib/labels';

export function LiveRun({ stream }: { stream: RunStream }) {
  const flags = stream.events.filter((e) => e.type === 'flag.created');
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_1fr]">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Radio className="size-4 animate-pulse-soft text-accent" aria-hidden />
            Auditing this claim
          </CardTitle>
          {stream.state === 'reconnecting' ? (
            <span className="inline-flex items-center gap-1.5 text-xs text-warning">
              <WifiOff className="size-3.5" aria-hidden />
              Reconnecting, progress is kept
            </span>
          ) : null}
        </CardHeader>
        <PipelineProgress events={stream.events} state={stream.state} className="p-3" />
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Flags found</CardTitle>
          <span className="text-xs text-ink-subtle tabular-nums">{flags.length}</span>
        </CardHeader>
        {flags.length === 0 ? (
          <p className="px-5 py-8 text-center text-ink-muted">
            Flags appear here as soon as the rules engine runs.
          </p>
        ) : (
          <ul className="divide-y divide-border" aria-live="polite">
            {flags.map((e) => {
              const d = e.data ?? {};
              const recoverable = typeof d.recoverable === 'number' ? d.recoverable : 0;
              const atRisk = typeof d.amount_at_risk === 'number' ? d.amount_at_risk : 0;
              const severity = (typeof d.severity === 'string' ? d.severity : 'info') as Parameters<
                typeof SeverityDot
              >[0]['severity'];
              return (
                <li key={e.seq} className="flex items-center gap-3 px-5 py-2.5 animate-fade-in">
                  <SeverityDot severity={severity} />
                  <span className="flex-1">{ruleTitle(String(d.rule_id ?? ''))}</span>
                  {recoverable ? (
                    <Money paise={recoverable} tone="recover" />
                  ) : (
                    <Money paise={atRisk} tone="risk" />
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </Card>
    </div>
  );
}
