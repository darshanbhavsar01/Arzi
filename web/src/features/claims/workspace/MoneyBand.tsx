/**
 * Billed → predicted payable → at risk → recoverable, and one bar splitting the bill into what
 * the engine expects to be paid and each kind of deduction. Every figure is engine output.
 */
import type { ReactNode } from 'react';

import type { AuditResult, ClaimMode } from '@/api/types';
import { Money } from '@/components/domain';
import { Tooltip } from '@/components/ui/overlays';
import { cn } from '@/lib/cn';
import { formatMoney, formatPercent } from '@/lib/format';
import { ruleTitle } from '@/lib/labels';

const OTHER = 'fill-band-other bg-band-other';
const BAND: Record<string, string> = {
  ROOM_RENT_EXCESS: 'fill-band-room bg-band-room',
  ICU_CAP: 'fill-band-room bg-band-room',
  PROP_ROOM_RENT: 'fill-band-prop bg-band-prop',
  NON_PAYABLE: 'fill-band-nonpay bg-band-nonpay',
  COPAY: 'fill-band-copay bg-band-copay',
};

/** The engine's deduction flags by rule. They sum exactly to the at-risk total, including
 * claim-level cuts such as co-payment that no single bill line carries. */
export function deductionSegments(audit: AuditResult): { ruleId: string; amount: number }[] {
  const byRule = new Map<string, number>();
  for (const flag of audit.flags) {
    if (flag.kind !== 'deduction') continue;
    byRule.set(flag.rule_id, (byRule.get(flag.rule_id) ?? 0) + flag.amount_at_risk);
  }
  return [...byRule.entries()]
    .filter(([, amount]) => amount > 0)
    .map(([ruleId, amount]) => ({ ruleId, amount }))
    .sort((a, b) => b.amount - a.amount);
}

function Figure({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs font-medium text-ink-muted">{label}</dt>
      <dd className="mt-1 text-[1.375rem] leading-tight font-semibold">{children}</dd>
      {hint ? <dd className="mt-0.5 text-xs text-ink-subtle">{hint}</dd> : null}
    </div>
  );
}

export function MoneyBand({ audit, mode }: { audit: AuditResult; mode: ClaimMode }) {
  const { totals } = audit;
  const segments = deductionSegments(audit);
  const billed = Math.max(totals.billed, 1);
  const payableWidth = (totals.predicted_payable / billed) * 100;
  // Each deduction starts where the previous one ends.
  const placed = segments.map((s, i) => ({
    ...s,
    x: payableWidth + (segments.slice(0, i).reduce((sum, p) => sum + p.amount, 0) / billed) * 100,
    width: (s.amount / billed) * 100,
  }));
  const appealing = mode !== 'pre_submission';

  return (
    <div className="rounded-xl border border-border bg-surface px-5 py-4 shadow-card">
      <dl className="grid grid-cols-2 gap-5 lg:grid-cols-4">
        <Figure label="Billed">
          <Money paise={totals.billed} />
        </Figure>
        <Figure
          label="Predicted payable"
          hint={`${formatPercent(totals.predicted_payable / billed)} of the bill`}
        >
          <Money paise={totals.predicted_payable} />
        </Figure>
        <Figure
          label="At risk"
          hint={appealing ? 'Deductions the rules uphold' : 'Likely deductions if filed as is'}
        >
          <Money paise={totals.at_risk} tone={totals.at_risk ? 'risk' : 'muted'} />
        </Figure>
        <Figure
          label={appealing ? 'Recoverable on appeal' : 'Saved by the fixes'}
          hint={
            appealing ? 'Insurer cuts the rules dispute' : 'If every fix is applied before filing'
          }
        >
          {appealing ? (
            <Money
              paise={totals.recoverable_on_appeal}
              tone={totals.recoverable_on_appeal ? 'recover' : 'muted'}
            />
          ) : (
            <Money paise={audit.fix_savings} tone={audit.fix_savings ? 'recover' : 'muted'} />
          )}
        </Figure>
      </dl>

      <div className="mt-4">
        <svg
          viewBox="0 0 100 4"
          preserveAspectRatio="none"
          className="h-2.5 w-full overflow-hidden rounded-full"
          role="img"
          aria-label={`Of ${formatMoney(totals.billed)} billed, ${formatMoney(totals.predicted_payable)} is predicted payable and ${formatMoney(totals.at_risk)} is at risk.`}
        >
          <rect x={0} y={0} width={payableWidth} height={4} className="fill-band-payable" />
          {placed.map((s) => (
            <rect
              key={s.ruleId}
              x={s.x}
              y={0}
              width={s.width}
              height={4}
              className={(BAND[s.ruleId] ?? OTHER).split(' ')[0]}
            />
          ))}
        </svg>
        <ul
          className="mt-2.5 flex flex-wrap gap-x-5 gap-y-1.5 text-xs text-ink-muted"
          aria-label="Breakdown"
        >
          <li className="inline-flex items-center gap-1.5">
            <span className="size-2.5 rounded-sm bg-band-payable" aria-hidden /> Payable{' '}
            <Money paise={totals.predicted_payable} className="text-ink" />
          </li>
          {segments.map((s) => (
            <li key={s.ruleId}>
              <Tooltip content={`${formatPercent(s.amount / billed)} of the bill`}>
                <button type="button" className="inline-flex items-center gap-1.5 rounded">
                  <span
                    className={cn('size-2.5 rounded-sm', (BAND[s.ruleId] ?? OTHER).split(' ')[1])}
                    aria-hidden
                  />
                  {ruleTitle(s.ruleId)} <Money paise={s.amount} className="text-ink" />
                </button>
              </Tooltip>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
