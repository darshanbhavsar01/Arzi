/** Findings sorted by ₹ impact. J / K move between them; each can be accepted or dismissed. */
import { CircleCheckBig, ListChecks } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';

import { useReviewFlag } from '@/api/queries';
import type { BillLine, ClaimRecord } from '@/api/types';
import { EmptyState } from '@/components/states';
import { Kbd } from '@/components/ui/primitives';
import { isTyping } from '@/lib/hooks';
import { FlagCard } from '@/features/claims/workspace/FlagCard';

function impact(flag: { kind: string; amount_at_risk: number; recoverable?: number }): number {
  return flag.kind === 'dispute' ? (flag.recoverable ?? 0) : flag.amount_at_risk;
}

export function FlagsTab({
  claim,
  onLine,
}: {
  claim: ClaimRecord;
  onLine: (line: BillLine) => void;
}) {
  const flags = [...(claim.audit?.flags ?? [])].sort((a, b) => impact(b) - impact(a));
  const [active, setActive] = useState(0);
  const cards = useRef<(HTMLElement | null)[]>([]);
  const review = useReviewFlag(claim.claim_id);
  const narratives = new Map((claim.narratives?.items ?? []).map((n) => [n.flag_id, n]));
  const reviews = new Map(claim.flag_reviews.map((r) => [r.flag_id, r]));
  const trace = claim.audit?.trace ?? [];
  const lines = claim.facts?.bill_lines ?? [];
  const clauses = claim.facts?.policy.clauses ?? [];

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (isTyping(event.target) || event.metaKey || event.ctrlKey || event.altKey) return;
      const key = event.key.toLowerCase();
      if (key !== 'j' && key !== 'k') return;
      event.preventDefault();
      setActive((i) => {
        const next = Math.min(flags.length - 1, Math.max(0, i + (key === 'j' ? 1 : -1)));
        cards.current[next]?.focus();
        cards.current[next]?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
        return next;
      });
    };
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('keydown', onKey);
    };
  }, [flags.length]);

  if (flags.length === 0) {
    return (
      <EmptyState
        className="m-4"
        icon={<CircleCheckBig aria-hidden />}
        title="No flags"
        description="The rules found nothing to deduct or dispute on this claim."
      />
    );
  }

  return (
    <div className="space-y-3 p-4">
      <h2 className="sr-only">Flags</h2>
      {claim.issues.length ? (
        <div className="rounded-lg border border-warning-border bg-warning-bg px-4 py-3 text-[0.8125rem] text-warning">
          <p className="flex items-center gap-2 font-medium">
            <ListChecks className="size-4" aria-hidden /> {claim.issues.length}{' '}
            {claim.issues.length === 1 ? 'item needs' : 'items need'} confirmation
          </p>
          <ul className="mt-1 list-disc space-y-0.5 pl-6">
            {claim.issues.map((issue, i) => (
              <li key={`${issue.code}-${String(i)}`}>{issue.message}</li>
            ))}
          </ul>
        </div>
      ) : null}
      <p className="flex items-center gap-1.5 text-xs text-ink-subtle">
        Sorted by ₹ impact · <Kbd>J</Kbd> <Kbd>K</Kbd> to move between flags
      </p>
      {flags.map((flag, i) => (
        <FlagCard
          key={flag.flag_id}
          ref={(node) => {
            cards.current[i] = node;
          }}
          flag={flag}
          active={i === active}
          narrative={narratives.get(flag.flag_id)}
          narrativeStatus={claim.narratives?.status}
          review={reviews.get(flag.flag_id)}
          trace={trace.filter((t) => t.rule_id === flag.rule_id)}
          lines={lines}
          clauses={clauses}
          onLine={onLine}
          reviewing={review.isPending}
          onReview={(decision, reason) => {
            review.mutate(
              { flagId: flag.flag_id, decision, ...(reason ? { reason } : {}) },
              {
                onSuccess: () =>
                  toast.success(decision === 'accepted' ? 'Flag accepted' : 'Flag dismissed', {
                    description: 'Recorded in the audit log.',
                  }),
                onError: () => toast.error('Could not save the decision'),
              },
            );
          }}
        />
      ))}
    </div>
  );
}
