/**
 * The policy terms the rules ran on (extracted, with their clauses) next to the policy
 * interpreter's independent reading. Disagreements and low confidence are marked to confirm.
 */
import { BookOpenCheck } from 'lucide-react';
import type { ReactNode } from 'react';

import type { ClaimRecord, Policy } from '@/api/types';
import { CitationChip } from '@/components/CitationChip';
import { Money, WarningNote } from '@/components/domain';
import { Badge, Card, CardHeader, CardTitle } from '@/components/ui/primitives';
import { formatPercent } from '@/lib/format';
import { POLICY_TERM } from '@/lib/labels';

interface Term {
  label: string;
  value: ReactNode;
  clause: string | null | undefined;
}

function terms(policy: Policy): Term[] {
  const cap = policy.room_rent_cap;
  const rows: Term[] = [
    { label: 'Sum insured', value: <Money paise={policy.sum_insured} />, clause: null },
    {
      label: 'Continuous cover',
      value: `${String(policy.continuous_cover_months)} months`,
      clause: null,
    },
  ];
  if (cap) {
    const value =
      cap.type === 'per_day_amount' ? (
        <>
          <Money paise={cap.amount} /> a day
        </>
      ) : cap.type === 'pct_of_si' ? (
        `${cap.pct}% of sum insured a day`
      ) : (
        cap.category
      );
    rows.push({ label: 'Room-rent cap', value, clause: cap.clause_id });
  }
  if (policy.proportionate_clause_id)
    rows.push({
      label: 'Proportionate deduction',
      value: 'Applies to associated expenses',
      clause: policy.proportionate_clause_id,
    });
  if (policy.icu_cap)
    rows.push({
      label: 'ICU cap',
      value: (
        <>
          <Money paise={policy.icu_cap.amount_per_day} /> a day
        </>
      ),
      clause: policy.icu_cap.clause_id,
    });
  if (policy.copay)
    rows.push({
      label: 'Co-payment',
      value: `${policy.copay.pct}% of the ${policy.copay.base === 'claimed' ? 'claimed' : 'admissible'} amount`,
      clause: policy.copay.clause_id,
    });
  for (const s of policy.sub_limits)
    rows.push({
      label: `Sub-limit: ${s.item}`,
      value: <Money paise={s.limit} />,
      clause: s.clause_id,
    });
  for (const w of policy.ped_declared)
    rows.push({
      label: `Pre-existing: ${w.condition}`,
      value: `${String(w.waiting_months)} months waiting`,
      clause: w.clause_id,
    });
  for (const w of policy.specific_waiting)
    rows.push({
      label: `Waiting: ${w.condition}`,
      value: `${String(w.waiting_months)} months`,
      clause: w.clause_id,
    });
  rows.push({
    label: 'Non-payable items cover',
    value: policy.non_payable_addon ? 'Opted' : 'Not opted',
    clause: null,
  });
  return rows;
}

export function PolicyTab({ claim }: { claim: ClaimRecord }) {
  const policy = claim.facts?.policy;
  const review = claim.policy_review;
  if (!policy) return null;
  const clauses = policy.clauses;

  return (
    <div className="space-y-4 p-4">
      <Card>
        <CardHeader>
          <div>
            <CardTitle>Terms the rules ran on</CardTitle>
            <p className="mt-0.5 text-xs text-ink-subtle">
              {policy.insurer}
              {policy.product ? ` · ${policy.product}` : ''}
            </p>
          </div>
        </CardHeader>
        <dl className="divide-y divide-border">
          {terms(policy).map((t) => (
            <div
              key={t.label}
              className="grid grid-cols-[12rem_1fr_auto] items-center gap-3 px-5 py-2.5"
            >
              <dt className="text-ink-muted">{t.label}</dt>
              <dd className="font-medium tabular-nums">{t.value}</dd>
              <dd>
                {t.clause ? <CitationChip refId={`policy:${t.clause}`} clauses={clauses} /> : null}
              </dd>
            </div>
          ))}
        </dl>
      </Card>

      <Card>
        <CardHeader>
          <div>
            <CardTitle className="flex items-center gap-2">
              <BookOpenCheck className="size-4 text-accent" aria-hidden /> Policy reading
            </CardTitle>
            <p className="mt-0.5 text-xs text-ink-subtle">
              A second, independent reading of the clauses by the policy interpreter
              {review?.prompt_ref ? ` (${review.prompt_ref})` : ''}.
            </p>
          </div>
          {review ? (
            <Badge
              tone={
                review.status === 'passed' || review.status === 'retried' ? 'success' : 'warning'
              }
            >
              {review.status === 'passed' || review.status === 'retried'
                ? 'Checks passed'
                : review.status.replace('_', ' ')}
            </Badge>
          ) : null}
        </CardHeader>
        {!review || review.terms.length === 0 ? (
          <p className="px-5 py-4 text-ink-muted">
            {review?.status === 'unavailable'
              ? 'The policy reading was not available for this audit.'
              : 'No policy reading for this audit.'}
          </p>
        ) : (
          <ul className="divide-y divide-border">
            {review.status === 'needs_review' ? (
              <li className="px-5 py-3">
                <WarningNote>
                  This reading did not pass every check; confirm each term against the clause.
                </WarningNote>
              </li>
            ) : null}
            {review.terms.map((note) => (
              <li key={`${note.term}-${note.clause_id ?? ''}`} className="px-5 py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{POLICY_TERM[note.term] ?? note.term}</span>
                  {note.clause_id ? (
                    <CitationChip refId={`policy:${note.clause_id}`} clauses={clauses} />
                  ) : null}
                  <span className="text-xs text-ink-subtle tabular-nums">
                    confidence {formatPercent(note.confidence)}
                  </span>
                  {note.needs_confirmation ? <Badge tone="warning">Confirm</Badge> : null}
                </div>
                {note.summary.text ? (
                  <p className="mt-1 text-ink-muted">{note.summary.text}</p>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
