import { describe, expect, it } from 'vitest';

import type { ClaimSummary } from '@/api/types';
import { summarise, weekStart } from '@/features/analytics/aggregate';

function claim(over: Partial<ClaimSummary>): ClaimSummary {
  return {
    claim_id: 'ARZ-1',
    mode: 'pre_submission',
    status: 'audited',
    insurer: 'Suraksha',
    patient: null,
    admitted_on: null,
    discharged_on: null,
    created_at: '2026-11-18T10:00:00Z',
    updated_at: null,
    totals: { billed: 100, predicted_payable: 60, at_risk: 40, recoverable_on_appeal: 25 },
    flag_count: 1,
    severities: [],
    needs_confirmation: 0,
    audit_seconds: 10,
    latest_appeal: null,
    ...over,
  };
}

describe('summarise', () => {
  it('totals only audited claims and builds the recovery funnel', () => {
    const stats = summarise(
      [
        claim({}),
        claim({
          claim_id: 'ARZ-2',
          insurer: 'Other',
          audit_seconds: 20,
          latest_appeal: {
            appeal_id: 'a',
            forum: 'insurer_gro',
            version: 1,
            status: 'signed',
          },
        }),
        claim({ claim_id: 'ARZ-3', totals: null, status: 'draft' }),
      ],
      (m) => m,
    );
    expect(stats.audited).toBe(2);
    expect(stats.atRisk).toBe(80);
    expect(stats.signed).toBe(1);
    expect(stats.avgAuditSeconds).toBe(15);
    expect(stats.byInsurer.map((b) => b.label)).toEqual(['Suraksha', 'Other']);
    expect(stats.funnel.map((b) => b.value)).toEqual([80, 50, 25, 25]);
  });

  it('has no average when nothing was timed', () => {
    expect(summarise([claim({ audit_seconds: null })], (m) => m).avgAuditSeconds).toBeNull();
  });

  it('groups dates by Monday', () => {
    expect(weekStart('2026-11-18T10:00:00Z')).toBe('2026-11-16');
    expect(weekStart('2026-11-22T23:00:00Z')).toBe('2026-11-16');
  });
});
