/** One finding: what, how much, why (checked prose), the evidence, the maths and the fix. */
import { Calculator, Check, ChevronDown, Lightbulb, X } from 'lucide-react';
import { forwardRef, useState } from 'react';

import type {
  BillLine,
  Flag,
  FlagNarrative,
  FlagReview,
  PolicyClause,
  ReasoningStatus,
  TraceStep,
} from '@/api/types';
import { CitationChip } from '@/components/CitationChip';
import { Money, SeverityLabel, WarningNote } from '@/components/domain';
import { Button } from '@/components/ui/button';
import { Dialog, DialogClose, DialogContent, DialogTrigger } from '@/components/ui/overlays';
import { Badge, Label, Textarea } from '@/components/ui/primitives';
import { cn } from '@/lib/cn';
import { FIX, ruleTitle } from '@/lib/labels';

const KIND = {
  deduction: { label: 'Likely deduction', tone: 'accent' as const },
  advisory: { label: 'Advisory', tone: 'info' as const },
  dispute: { label: 'Insurer error', tone: 'success' as const },
};

interface FlagCardProps {
  flag: Flag;
  narrative: FlagNarrative | undefined;
  narrativeStatus: ReasoningStatus | undefined;
  review: FlagReview | undefined;
  trace: TraceStep[];
  lines: BillLine[];
  clauses: PolicyClause[];
  active: boolean;
  onLine: (line: BillLine) => void;
  onReview: (decision: 'accepted' | 'dismissed', reason?: string) => void;
  reviewing: boolean;
}

export const FlagCard = forwardRef<HTMLElement, FlagCardProps>(function FlagCard(
  {
    flag,
    narrative,
    narrativeStatus,
    review,
    trace,
    lines,
    clauses,
    active,
    onLine,
    onReview,
    reviewing,
  },
  ref,
) {
  const [maths, setMaths] = useState(false);
  const [reason, setReason] = useState('');
  const [dismissing, setDismissing] = useState(false);
  const kind = KIND[flag.kind];
  const dispute = flag.kind === 'dispute';
  const amount = dispute ? flag.recoverable : flag.amount_at_risk;
  const flagLines = lines.filter((l) => flag.lines.includes(l.line_id));
  const headingId = `flag-${flag.flag_id}`;

  return (
    <article
      ref={ref}
      tabIndex={-1}
      aria-labelledby={headingId}
      className={cn(
        'rounded-xl border bg-surface p-4 shadow-card transition-shadow focus-visible:outline-2',
        active ? 'border-navy ring-1 ring-navy' : 'border-border',
        review?.decision === 'dismissed' && 'opacity-70',
      )}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 space-y-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <SeverityLabel severity={flag.severity} />
            <Badge tone={kind.tone}>{kind.label}</Badge>
            {review ? (
              <Badge tone={review.decision === 'accepted' ? 'navy' : 'neutral'}>
                {review.decision === 'accepted' ? <Check aria-hidden /> : <X aria-hidden />}
                {review.decision === 'accepted' ? 'Accepted' : 'Dismissed'}
              </Badge>
            ) : null}
          </div>
          <h3 id={headingId} className="text-[0.9375rem] font-semibold leading-snug">
            {narrative?.headline.text ?? ruleTitle(flag.rule_id)}
          </h3>
          {narrative?.headline.text ? (
            <p className="text-xs text-ink-subtle">{ruleTitle(flag.rule_id)}</p>
          ) : null}
        </div>
        <div className="shrink-0 text-right">
          <Money
            paise={amount}
            tone={dispute ? 'recover' : flag.kind === 'deduction' ? 'risk' : 'default'}
            className="text-lg"
          />
          <p className="text-xs text-ink-subtle">
            {dispute ? 'recoverable' : flag.kind === 'deduction' ? 'at risk' : 'exposure'}
          </p>
        </div>
      </div>

      {narrative?.explanation.text ? (
        <p className="mt-3 leading-relaxed text-ink">{narrative.explanation.text}</p>
      ) : narrativeStatus === 'needs_review' ? (
        <div className="mt-3">
          <WarningNote>
            The explanation did not pass Arzi’s checks, so it is hidden. The finding and amount come
            from the rules engine.
          </WarningNote>
        </div>
      ) : (
        <p className="mt-3 text-[0.8125rem] text-ink-subtle">
          Explanation not available for this audit; the finding and amount come from the rules
          engine.
        </p>
      )}

      {flagLines.length ? (
        <div className="mt-3 flex flex-wrap gap-1.5" aria-label="Bill lines">
          {flagLines.map((line) => (
            <button
              key={line.line_id}
              type="button"
              onClick={() => {
                onLine(line);
              }}
              className="rounded-md border border-border bg-canvas px-2 py-0.5 text-xs text-ink-muted hover:border-navy hover:text-navy"
            >
              Line {line.line_id} · {line.description}
            </button>
          ))}
        </div>
      ) : null}

      {flag.citation_refs.length ? (
        <div className="mt-3 flex flex-wrap gap-1.5" aria-label="Citations">
          {flag.citation_refs.map((ref) => (
            <CitationChip key={ref} refId={ref} clauses={clauses} />
          ))}
        </div>
      ) : null}

      {flag.fix_code ? (
        <div className="mt-4 flex items-start gap-3 rounded-lg bg-cream px-3 py-2.5">
          <Lightbulb className="mt-0.5 size-4 shrink-0 text-accent" aria-hidden />
          <div className="min-w-0 flex-1 text-[0.8125rem]">
            <p className="font-medium text-ink">{FIX[flag.fix_code] ?? flag.fix_code}</p>
            {narrative?.fix.text ? (
              <p className="mt-0.5 text-ink-muted">{narrative.fix.text}</p>
            ) : null}
          </div>
          {flag.fix_savings ? (
            <span className="shrink-0 text-right text-xs text-ink-muted">
              saves up to
              <br />
              <Money paise={flag.fix_savings} tone="recover" />
            </span>
          ) : null}
        </div>
      ) : null}

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-border pt-3">
        <Button
          variant="ghost"
          size="sm"
          aria-expanded={maths}
          onClick={() => {
            setMaths(!maths);
          }}
        >
          <Calculator aria-hidden />
          Show the maths
          <ChevronDown className={cn('transition-transform', maths && 'rotate-180')} aria-hidden />
        </Button>
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            disabled={reviewing || review?.decision === 'accepted'}
            onClick={() => {
              onReview('accepted');
            }}
          >
            <Check aria-hidden /> Accept
          </Button>
          <Dialog open={dismissing} onOpenChange={setDismissing}>
            <DialogTrigger asChild>
              <Button variant="ghost" size="sm" disabled={reviewing}>
                <X aria-hidden /> Dismiss
              </Button>
            </DialogTrigger>
            <DialogContent
              title="Dismiss this flag"
              description="The reason is saved to the claim’s audit log with your name."
            >
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  onReview('dismissed', reason.trim());
                  setDismissing(false);
                }}
                className="space-y-3"
              >
                <Label htmlFor={`reason-${flag.flag_id}`}>Reason</Label>
                <Textarea
                  id={`reason-${flag.flag_id}`}
                  value={reason}
                  onChange={(e) => {
                    setReason(e.target.value);
                  }}
                  placeholder="For example: the patient signed the room-upgrade consent"
                  required
                />
                <div className="flex justify-end gap-2">
                  <DialogClose asChild>
                    <Button variant="ghost">Cancel</Button>
                  </DialogClose>
                  <Button type="submit" disabled={!reason.trim()}>
                    Dismiss flag
                  </Button>
                </div>
              </form>
            </DialogContent>
          </Dialog>
        </div>
      </div>
      {review?.decision === 'dismissed' && review.reason ? (
        <p className="mt-2 text-xs text-ink-muted">Dismissed: {review.reason}</p>
      ) : null}

      {maths ? (
        <ol className="mt-3 space-y-1.5 rounded-lg bg-sunken p-3 font-mono text-xs text-ink-muted">
          {trace.map((step) => (
            <li key={step.step_id} className="flex gap-2">
              <span className="text-ink-subtle">{step.step_id}</span>
              <span className="text-ink">{step.formula}</span>
            </li>
          ))}
          {trace.length === 0 ? (
            <li>No computation: this finding is a rule check without a ₹ calculation.</li>
          ) : null}
        </ol>
      ) : null}
    </article>
  );
});
