/** The editor's right rail: references (with the Verify acknowledgement), enclosures, versions. */
import { Check, History, Paperclip, TriangleAlert } from 'lucide-react';

import { useCitations } from '@/api/queries';
import type { AppealVersion, PolicyClause } from '@/api/types';
import { CitationChip } from '@/components/CitationChip';
import { Badge, Card, CardHeader, CardTitle, Checkbox, Label } from '@/components/ui/primitives';
import { cn } from '@/lib/cn';
import { formatDateTime } from '@/lib/format';
import { APPEAL_STATUS, FORUM } from '@/lib/labels';

export function verifyRefs(
  appeal: AppealVersion,
  registry: Map<string, { status: string }> | undefined,
): string[] {
  const refs = [...new Set(appeal.content.items.flatMap((i) => i.citations))];
  return refs.filter((r) => registry?.get(r)?.status === 'verify');
}

export function AppealRail({
  appeal,
  versions,
  viewing,
  onView,
  clauses,
  acknowledged,
  onAcknowledge,
}: {
  appeal: AppealVersion;
  versions: AppealVersion[];
  viewing: number;
  onView: (version: number) => void;
  clauses: PolicyClause[];
  acknowledged: boolean;
  onAcknowledge: (value: boolean) => void;
}) {
  const { data: registry } = useCitations();
  const refs = [...new Set(appeal.content.items.flatMap((i) => i.citations))];
  const toVerify = verifyRefs(appeal, registry);
  const editableState = appeal.status === 'draft' || appeal.status === 'in_review';

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>References used</CardTitle>
          <span className="text-xs text-ink-subtle">{refs.length}</span>
        </CardHeader>
        <div className="space-y-3 p-4">
          <div className="flex flex-wrap gap-1.5">
            {refs.map((r) => (
              <CitationChip key={r} refId={r} clauses={clauses} />
            ))}
          </div>
          {toVerify.length && editableState ? (
            <div className="rounded-lg border border-warning-border bg-warning-bg p-3">
              <p className="flex items-center gap-1.5 text-[0.8125rem] font-medium text-warning">
                <TriangleAlert className="size-4" aria-hidden />
                {toVerify.length} {toVerify.length === 1 ? 'reference is' : 'references are'} marked
                Verify
              </p>
              <div className="mt-2 flex items-start gap-2">
                <Checkbox
                  id="ack-verify"
                  checked={acknowledged}
                  onCheckedChange={(v) => {
                    onAcknowledge(v === true);
                  }}
                  className="mt-0.5"
                />
                <Label htmlFor="ack-verify" className="font-normal leading-snug text-warning">
                  I have checked these against the primary source before filing.
                </Label>
              </div>
            </div>
          ) : null}
        </div>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Paperclip className="size-4 text-accent" aria-hidden />
            Enclosures
          </CardTitle>
        </CardHeader>
        <ul className="space-y-1.5 p-4 text-[0.8125rem]">
          {appeal.content.enclosures.map((e) => (
            <li key={e} className="flex items-start gap-2">
              <Check className="mt-0.5 size-3.5 shrink-0 text-success" aria-hidden />
              {e}
            </li>
          ))}
        </ul>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <History className="size-4 text-accent" aria-hidden />
            Versions
          </CardTitle>
        </CardHeader>
        <ol className="divide-y divide-border">
          {[...versions].reverse().map((v) => (
            <li key={v.version}>
              <button
                type="button"
                onClick={() => {
                  onView(v.version);
                }}
                aria-current={v.version === viewing ? 'true' : undefined}
                className={cn(
                  'flex w-full items-start justify-between gap-2 px-4 py-2.5 text-left hover:bg-canvas',
                  v.version === viewing && 'bg-navy-soft/60',
                )}
              >
                <span>
                  <span className="font-medium">Version {v.version}</span>
                  <span className="block text-xs text-ink-subtle">
                    {v.prompt_ref
                      ? 'Drafted by Arzi'
                      : `Edited${v.based_on ? ` from v${String(v.based_on)}` : ''}`}{' '}
                    · {FORUM[v.forum].short} · {formatDateTime(v.created_at)}
                  </span>
                </span>
                <Badge
                  tone={
                    v.status === 'signed' || v.status === 'exported'
                      ? 'navy'
                      : v.status === 'in_review'
                        ? 'info'
                        : 'warning'
                  }
                >
                  {APPEAL_STATUS[v.status].split(' —')[0]}
                </Badge>
              </button>
            </li>
          ))}
        </ol>
      </Card>
    </div>
  );
}
