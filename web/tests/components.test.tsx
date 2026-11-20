import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ColumnDef } from '@tanstack/react-table';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import type { AppealVersion } from '@/api/types';
import { DataTable } from '@/components/DataTable';
import { TooltipProvider } from '@/components/ui/overlays';
import { verifyRefs } from '@/features/appeal/AppealRail';
import { appealAsText, WithLockedAmounts } from '@/features/appeal/appealText';
import { SignDialog } from '@/features/appeal/SignDialog';

function wrap(node: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <TooltipProvider>{node}</TooltipProvider>
    </QueryClientProvider>,
  );
}

interface Row {
  id: string;
  amount: number;
}

const columns: ColumnDef<Row>[] = [
  { id: 'id', accessorFn: (r) => r.id, header: 'Claim' },
  { id: 'amount', accessorFn: (r) => r.amount, header: 'Amount', meta: { align: 'right' } },
];

describe('DataTable', () => {
  const rows = [
    { id: 'B', amount: 900 },
    { id: 'A', amount: 19_237 },
    { id: 'C', amount: 310_000 },
  ];

  it('sorts by a column and announces the order (amounts largest first)', async () => {
    wrap(<DataTable caption="Claims" data={rows} columns={columns} getRowId={(r) => r.id} />);
    const header = screen.getByRole('columnheader', { name: /Amount/ });
    const ids = () =>
      screen
        .getAllByRole('row')
        .slice(1)
        .map((r) => within(r).getAllByRole('cell')[0]?.textContent);
    await userEvent.click(within(header).getByRole('button'));
    expect(header).toHaveAttribute('aria-sort', 'descending');
    expect(ids()).toEqual(['C', 'A', 'B']);
    await userEvent.click(within(header).getByRole('button'));
    expect(header).toHaveAttribute('aria-sort', 'ascending');
    expect(ids()).toEqual(['B', 'A', 'C']);
  });

  it('moves between rows with the arrow keys and opens with Enter', async () => {
    const onOpen = vi.fn();
    wrap(
      <DataTable
        caption="Claims"
        data={rows}
        columns={columns}
        getRowId={(r) => r.id}
        onOpen={onOpen}
      />,
    );
    const [, first, second] = screen.getAllByRole('row');
    first?.focus();
    await userEvent.keyboard('{ArrowDown}');
    expect(second).toHaveFocus();
    await userEvent.keyboard('{Enter}');
    expect(onOpen).toHaveBeenCalledWith(rows[1]);
  });
});

const appeal: AppealVersion = {
  claim_id: 'ARZ-1',
  version: 2,
  forum: 'insurer_gro',
  status: 'in_review',
  drafting: 'passed',
  prompt_ref: null,
  violations: [],
  based_on: 1,
  idempotency_key: null,
  created_by: 'demo-desk-01',
  created_at: '2026-11-20T09:00:00Z',
  signature: null,
  exported_at: null,
  content: {
    subject: { template: 'Review', text: 'Review' },
    facts: { template: 'Paid {{letter.approved}}.', text: 'Paid ₹1,38,375.' },
    relief: { template: 'Pay {{totals.recoverable}}.', text: 'Pay ₹20,137.50.' },
    relief_amount: 2_013_750,
    enclosures: ['Copy of the insurer’s letter'],
    items: [
      {
        flag_id: 'SUBSUMED_ITEM',
        rule_id: 'SUBSUMED_ITEM',
        amount: 90_000,
        amount_ref: 'flag.SUBSUMED_ITEM.recoverable',
        insurer_reason: 'Deducted as a non-payable item',
        argument: { template: 'x', text: 'Registration is subsumed.' },
        citations: ['IRDAI_NON_PAYABLE_ANNEX_I', 'policy:8.1'],
      },
    ],
  },
};

describe('appeal text', () => {
  it('marks every rendered rupee figure as a locked engine amount', () => {
    render(<p>{WithLockedAmounts({ text: 'Approved ₹1,38,375 of ₹2,26,500.50 claimed.' })}</p>);
    expect(
      screen.getAllByTitle('Amount from the rules engine, locked').map((n) => n.textContent),
    ).toEqual([
      '₹1,38,375 (locked amount from the rules engine)',
      '₹2,26,500.50 (locked amount from the rules engine)',
    ]);
  });

  it('copies as plain text for portal forms', () => {
    const text = appealAsText(appeal);
    expect(text).toContain('To: Insurer grievance officer (GRO)');
    expect(text).toContain('Item that is part of room or procedure cost: ₹900.00');
    expect(text).toContain('Pay ₹20,137.50.');
  });

  it('lists only the references still marked verify', () => {
    const registry = new Map([
      ['IRDAI_NON_PAYABLE_ANNEX_I', { status: 'verify' }],
      ['IRDAI_PROP_DED_2020', { status: 'verified' }],
    ]);
    expect(verifyRefs(appeal, registry)).toEqual(['IRDAI_NON_PAYABLE_ANNEX_I']);
  });
});

describe('sign gate', () => {
  it('cannot sign without a named reviewer, a role and the declaration', async () => {
    wrap(<SignDialog claimId="ARZ-1" appeal={appeal} open onOpenChange={() => undefined} />);
    const sign = screen.getByRole('button', { name: 'Sign appeal' });
    expect(sign).toBeDisabled();
    await userEvent.type(screen.getByLabelText('Reviewer’s full name'), 'Riya Mehta');
    await userEvent.type(screen.getByLabelText('Role'), 'TPA desk manager');
    expect(sign).toBeDisabled();
    await userEvent.click(screen.getByRole('checkbox'));
    expect(sign).toBeEnabled();
  });

  it('shows the content hash and the export once signed', () => {
    const signed = {
      ...appeal,
      status: 'signed' as const,
      signature: {
        reviewer_name: 'Riya Mehta',
        reviewer_role: 'TPA desk manager',
        signed_by: 'demo-desk-01',
        signed_at: '2026-11-20T09:05:00Z',
        content_sha256: 'ab'.repeat(32),
      },
    };
    wrap(<SignDialog claimId="ARZ-1" appeal={signed} open onOpenChange={() => undefined} />);
    expect(screen.getByText('ab'.repeat(32))).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Export signed PDF/ })).toHaveAttribute(
      'href',
      '/api/v1/claims/ARZ-1/appeals/2/export.pdf',
    );
  });
});
