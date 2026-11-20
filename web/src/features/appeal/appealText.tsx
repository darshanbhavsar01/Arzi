/** Appeal text helpers: locked amount chips, placeholder vocabulary, and the copy-as-text form. */
import { Lock } from 'lucide-react';
import type { ReactNode } from 'react';

import type { AppealVersion, ClaimRecord } from '@/api/types';
import { formatMoney } from '@/lib/format';
import { FORUM, ruleTitle } from '@/lib/labels';

/** Every ₹ figure in rendered appeal text was filled from the engine (the amount guard rejects
 * any other), so highlighting them shows exactly which amounts are locked. */
const RENDERED_AMOUNT = /₹[\d,]+(?:\.\d{1,2})?/g;

export function WithLockedAmounts({ text }: { text: string }): ReactNode {
  const parts: ReactNode[] = [];
  let last = 0;
  for (const match of text.matchAll(RENDERED_AMOUNT)) {
    const at = match.index;
    if (at > last) parts.push(text.slice(last, at));
    parts.push(
      <span
        key={at}
        className="mx-0.5 inline-flex items-center gap-1 rounded-md border border-navy/20 bg-navy-soft px-1.5 font-medium whitespace-nowrap tabular-nums text-navy"
        title="Amount from the rules engine, locked"
      >
        <Lock className="size-3" aria-hidden />
        {match[0]}
        <span className="sr-only"> (locked amount from the rules engine)</span>
      </span>,
    );
    last = at + match[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

export interface PlaceholderOption {
  token: string;
  label: string;
  value: number;
}

/** The amounts an editor may insert, with the values they will render to. */
export function placeholderOptions(claim: ClaimRecord): PlaceholderOption[] {
  const audit = claim.audit;
  if (!audit) return [];
  const options: PlaceholderOption[] = [
    {
      token: '{{totals.recoverable}}',
      label: 'Total relief sought',
      value: audit.totals.recoverable_on_appeal,
    },
    { token: '{{totals.billed}}', label: 'Total billed', value: audit.totals.billed },
  ];
  const letter = claim.facts?.insurer_letter;
  if (letter) {
    options.push({
      token: '{{letter.claimed}}',
      label: 'Amount claimed (letter)',
      value: letter.amount_claimed,
    });
    options.push({
      token: '{{letter.approved}}',
      label: 'Amount approved (letter)',
      value: letter.amount_approved,
    });
  }
  for (const flag of audit.flags) {
    if (flag.kind === 'dispute' && flag.recoverable) {
      options.push({
        token: `{{flag.${flag.flag_id}.recoverable}}`,
        label: ruleTitle(flag.rule_id),
        value: flag.recoverable,
      });
    }
  }
  return options;
}

/** The signed letter body as plain text, for pasting into a portal form (Bima Bharosa). */
export function appealAsText(appeal: AppealVersion): string {
  const c = appeal.content;
  const items = c.items
    .map(
      (item, i) =>
        `${String(i + 1)}. ${ruleTitle(item.rule_id)}: ${formatMoney(item.amount, { exact: true })}\n   Insurer's reason: ${item.insurer_reason}\n   Our grounds: ${item.argument.text ?? ''}`,
    )
    .join('\n\n');
  const signed = appeal.signature
    ? `\n\nReviewed and signed by ${appeal.signature.reviewer_name}, ${appeal.signature.reviewer_role}\nContent SHA-256: ${appeal.signature.content_sha256}`
    : '';
  return (
    [
      `To: ${FORUM[appeal.forum].label}`,
      `Subject: ${c.subject.text ?? ''}`,
      c.facts.text ?? '',
      `Items in dispute\n${items}`,
      c.relief.text ?? '',
      c.enclosures.length
        ? `Enclosures\n${c.enclosures.map((e, i) => `${String(i + 1)}. ${e}`).join('\n')}`
        : '',
    ]
      .filter(Boolean)
      .join('\n\n') + signed
  );
}
