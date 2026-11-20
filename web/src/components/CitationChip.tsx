/**
 * A cited reference: an IRDAI rule from the whitelist or a clause of this claim's policy. The
 * popover shows what it says and where it comes from; refs still marked `verify` carry an amber
 * "Verify before filing" badge, so nothing unconfirmed is presented as settled regulation.
 */
import { BadgeCheck, BookOpen, FileText, TriangleAlert } from 'lucide-react';

import { useCitations } from '@/api/queries';
import type { PolicyClause } from '@/api/types';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/overlays';
import { Badge } from '@/components/ui/primitives';
import { cn } from '@/lib/cn';

const POLICY = 'policy:';

export function CitationChip({
  refId,
  clauses = [],
}: {
  refId: string;
  clauses?: readonly PolicyClause[];
}) {
  const { data: registry } = useCitations();
  const isPolicy = refId.startsWith(POLICY);
  const clauseId = refId.slice(POLICY.length);
  const clause = isPolicy ? clauses.find((c) => c.id === clauseId) : undefined;
  const entry = isPolicy ? undefined : registry?.get(refId);
  const verify = entry?.status === 'verify';
  const label = isPolicy ? `Clause ${clauseId}` : (entry?.title ?? refId);

  return (
    <Popover>
      <PopoverTrigger
        className={cn(
          'inline-flex max-w-full items-center gap-1 rounded-md border px-1.5 py-0.5 text-xs font-medium hover:bg-sunken',
          verify
            ? 'border-warning-border bg-warning-bg text-warning'
            : 'border-border bg-surface text-ink-muted',
        )}
      >
        {isPolicy ? (
          <FileText className="size-3 shrink-0" aria-hidden />
        ) : (
          <BookOpen className="size-3 shrink-0" aria-hidden />
        )}
        <span className="truncate">{label}</span>
        {verify ? (
          <TriangleAlert className="size-3 shrink-0" aria-label="Verify before filing" />
        ) : null}
      </PopoverTrigger>
      <PopoverContent className="w-96">
        {isPolicy ? (
          <>
            <div className="flex items-center justify-between gap-2">
              <p className="text-xs font-medium text-ink-subtle">Policy clause {clauseId}</p>
              <Badge tone="info">From this policy</Badge>
            </div>
            <p className="mt-1 font-semibold">
              {clause?.title ?? 'Clause cited by the policy schedule'}
            </p>
            {clause?.text ? (
              <blockquote className="mt-2 border-l-2 border-slate pl-3 text-[0.8125rem] leading-relaxed text-ink-muted">
                {clause.text}
              </blockquote>
            ) : null}
            {clause?.page ? (
              <p className="mt-2 text-xs text-ink-subtle">Policy wording, page {clause.page}</p>
            ) : null}
          </>
        ) : entry ? (
          <>
            <div className="flex items-center justify-between gap-2">
              <p className="font-mono text-xs text-ink-subtle">{entry.id}</p>
              {verify ? (
                <Badge tone="warning">
                  <TriangleAlert aria-hidden />
                  Verify before filing
                </Badge>
              ) : (
                <Badge tone="success">
                  <BadgeCheck aria-hidden />
                  Verified
                </Badge>
              )}
            </div>
            <p className="mt-1 font-semibold">{entry.title}</p>
            <p className="mt-2 text-[0.8125rem] leading-relaxed text-ink-muted">
              {entry.summary_en}
            </p>
            <dl className="mt-3 space-y-1 text-xs text-ink-subtle">
              <div>
                <dt className="inline font-medium text-ink-muted">Source: </dt>
                <dd className="inline">{entry.source_doc}</dd>
              </div>
              <div>
                <dt className="inline font-medium text-ink-muted">Reference: </dt>
                <dd className="inline">{entry.ref}</dd>
              </div>
            </dl>
          </>
        ) : (
          <p className="text-ink-muted">
            This reference is not in Arzi’s citation list (unverified).
          </p>
        )}
      </PopoverContent>
    </Popover>
  );
}
