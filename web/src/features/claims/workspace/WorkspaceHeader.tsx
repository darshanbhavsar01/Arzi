/** Claim identity, state and the next actions (re-run, draft or open the appeal). */
import { CalendarRange, FileSignature, RotateCw, Scale } from 'lucide-react';
import { Link } from 'react-router';

import type { ClaimRecord } from '@/api/types';
import { RedactionBadge, StatusPill } from '@/components/domain';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/primitives';
import { formatDate } from '@/lib/format';
import { ShareDialog } from '@/features/claims/workspace/ShareDialog';
import { MODE } from '@/lib/labels';

export function canAppeal(claim: ClaimRecord): boolean {
  return (
    claim.mode !== 'pre_submission' &&
    (claim.audit?.flags ?? []).some((f) => f.kind === 'dispute' && f.appealable)
  );
}

export function WorkspaceHeader({
  claim,
  onRerun,
  rerunning,
}: {
  claim: ClaimRecord;
  onRerun: () => void;
  rerunning: boolean;
}) {
  const facts = claim.facts;
  const hasAppeal = claim.appeals.length > 0;
  const rerunnable = claim.status === 'audited' || claim.status === 'failed';

  return (
    <header className="flex flex-wrap items-start justify-between gap-4">
      <div className="min-w-0 space-y-1.5">
        <p className="text-xs font-medium text-ink-subtle">
          <Link to="/worklist" className="hover:text-ink hover:underline">
            Worklist
          </Link>{' '}
          / Claim
        </p>
        <div className="flex flex-wrap items-center gap-2.5">
          <h1 className="font-mono text-xl font-semibold tracking-tight">{claim.claim_id}</h1>
          <StatusPill status={claim.status} />
          <Badge>{MODE[claim.mode].label}</Badge>
          {claim.redaction ? <RedactionBadge counts={claim.redaction.counts ?? {}} /> : null}
        </div>
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-ink-muted">
          <span>
            Patient <span className="font-mono text-ink">{facts?.patient.redacted_id ?? '—'}</span>
            {facts?.patient.age ? `, ${String(facts.patient.age)} y` : ''}
          </span>
          <span aria-hidden>·</span>
          <span>{facts?.policy.insurer ?? claim.insurer_hint ?? 'Insurer from the policy'}</span>
          {facts?.admission.date_in ? (
            <>
              <span aria-hidden>·</span>
              <span className="inline-flex items-center gap-1">
                <CalendarRange className="size-3.5" aria-hidden />
                {formatDate(facts.admission.date_in, { short: true })} →{' '}
                {formatDate(facts.admission.date_out)}
              </span>
            </>
          ) : null}
          {facts?.admission.procedure ? (
            <>
              <span aria-hidden>·</span>
              <span>{facts.admission.procedure}</span>
            </>
          ) : null}
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {claim.audit ? <ShareDialog claimId={claim.claim_id} /> : null}
        {rerunnable ? (
          <Button variant="secondary" onClick={onRerun} loading={rerunning}>
            {rerunning ? null : <RotateCw aria-hidden />}
            Re-run audit
          </Button>
        ) : null}
        {hasAppeal ? (
          <Button asChild>
            <Link to={`/claims/${claim.claim_id}/appeal`}>
              <FileSignature aria-hidden />
              Open appeal
            </Link>
          </Button>
        ) : canAppeal(claim) ? (
          <Button asChild variant="accent">
            <Link to={`/claims/${claim.claim_id}/appeal`}>
              <Scale aria-hidden />
              Draft appeal
            </Link>
          </Button>
        ) : null}
      </div>
    </header>
  );
}
