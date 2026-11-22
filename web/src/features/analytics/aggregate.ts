/** Desk analytics computed from worklist summaries: pure, so the numbers are unit-tested. */
import type { ClaimSummary } from '@/api/types';

export interface Bar {
  label: string;
  value: number;
}

export interface Analytics {
  audited: number;
  atRisk: number;
  recoverable: number;
  signed: number;
  avgAuditSeconds: number | null;
  byInsurer: Bar[];
  byMode: Bar[];
  weekly: Bar[];
  funnel: Bar[];
}

const SIGNED = new Set(['signed', 'exported']);

/** What the audit found on a claim: the likely deduction, or for a rejection (nothing "at risk"
 * because nothing is payable) the disputed amount an appeal can recover. */
export function exposure(c: ClaimSummary): number {
  return Math.max(c.totals?.at_risk ?? 0, c.totals?.recoverable_on_appeal ?? 0);
}

/** Monday of the claim's week, as a sortable ISO date. */
export function weekStart(iso: string): string {
  const d = new Date(iso);
  const day = (d.getUTCDay() + 6) % 7;
  d.setUTCDate(d.getUTCDate() - day);
  return d.toISOString().slice(0, 10);
}

function sumBy(rows: ClaimSummary[], key: (c: ClaimSummary) => string | null): Bar[] {
  const totals = new Map<string, number>();
  for (const c of rows) {
    const k = key(c);
    if (k) totals.set(k, (totals.get(k) ?? 0) + (c.totals?.at_risk ?? 0));
  }
  return [...totals].map(([label, value]) => ({ label, value })).sort((a, b) => b.value - a.value);
}

export function summarise(
  claims: ClaimSummary[],
  modeLabel: (mode: ClaimSummary['mode']) => string,
): Analytics {
  const audited = claims.filter((c) => c.totals !== null);
  const sum = (f: (c: ClaimSummary) => number) => audited.reduce((n, c) => n + f(c), 0);
  const seconds = audited.flatMap((c) => (c.audit_seconds === null ? [] : [c.audit_seconds]));
  const appealed = audited.filter((c) => c.latest_appeal !== null);
  const signed = appealed.filter((c) => c.latest_appeal && SIGNED.has(c.latest_appeal.status));
  const atRisk = sum((c) => c.totals?.at_risk ?? 0);
  const weekly = sumBy(audited, (c) => (c.created_at ? weekStart(c.created_at) : null)).sort(
    (a, b) => a.label.localeCompare(b.label),
  );
  return {
    audited: audited.length,
    atRisk,
    recoverable: sum((c) => c.totals?.recoverable_on_appeal ?? 0),
    signed: signed.length,
    avgAuditSeconds: seconds.length ? seconds.reduce((a, b) => a + b, 0) / seconds.length : null,
    byInsurer: sumBy(audited, (c) => c.insurer),
    byMode: sumBy(audited, (c) => modeLabel(c.mode)),
    weekly,
    funnel: [
      { label: 'At risk or disputed', value: sum(exposure) },
      {
        label: 'Appealable',
        value: sum((c) => c.totals?.recoverable_on_appeal ?? 0),
      },
      {
        label: 'Appeal drafted',
        value: appealed.reduce((n, c) => n + (c.totals?.recoverable_on_appeal ?? 0), 0),
      },
      {
        label: 'Signed by a reviewer',
        value: signed.reduce((n, c) => n + (c.totals?.recoverable_on_appeal ?? 0), 0),
      },
    ],
  };
}
