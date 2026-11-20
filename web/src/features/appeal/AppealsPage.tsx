/** Appeals across the desk: drafts, in review, signed and exported, and claims ready to draft. */
import type { ColumnDef } from '@tanstack/react-table';
import { Scale } from 'lucide-react';
import { useMemo } from 'react';
import { Link, useNavigate } from 'react-router';

import { useClaims } from '@/api/queries';
import type { ClaimSummary } from '@/api/types';
import { DataTable } from '@/components/DataTable';
import { Money } from '@/components/domain';
import { EmptyState, PageHeader, ProblemAlert, TableSkeleton } from '@/components/states';
import { Button } from '@/components/ui/button';
import { Badge, Card } from '@/components/ui/primitives';
import { formatRelative } from '@/lib/format';
import { APPEAL_STATUS, FORUM, MODE } from '@/lib/labels';

const columns: ColumnDef<ClaimSummary>[] = [
  {
    id: 'claim',
    accessorFn: (c) => c.claim_id,
    header: 'Claim',
    enableHiding: false,
    meta: { label: 'Claim' },
    cell: ({ row }) => (
      <span className="font-mono text-[0.8125rem] font-medium text-navy">
        {row.original.claim_id}
      </span>
    ),
  },
  {
    id: 'mode',
    accessorFn: (c) => MODE[c.mode].short,
    header: 'Decision',
    meta: { label: 'Decision' },
  },
  {
    id: 'insurer',
    accessorFn: (c) => c.insurer ?? '',
    header: 'Insurer',
    meta: { label: 'Insurer' },
    cell: ({ getValue }) => <span className="block max-w-56 truncate">{String(getValue())}</span>,
  },
  {
    id: 'forum',
    accessorFn: (c) => (c.latest_appeal ? FORUM[c.latest_appeal.forum].short : ''),
    header: 'Forum',
    meta: { label: 'Forum' },
    cell: ({ getValue }) =>
      String(getValue()) || <span className="text-ink-subtle">Not drafted</span>,
  },
  {
    id: 'version',
    accessorFn: (c) => c.latest_appeal?.version ?? 0,
    header: 'Version',
    meta: { label: 'Version', align: 'right' },
    cell: ({ getValue }) => (Number(getValue()) ? `v${String(getValue())}` : '—'),
  },
  {
    id: 'sought',
    accessorFn: (c) => c.totals?.recoverable_on_appeal ?? 0,
    header: 'Amount sought',
    meta: { label: 'Amount sought', align: 'right' },
    cell: ({ row }) => (
      <Money paise={row.original.totals?.recoverable_on_appeal ?? 0} tone="recover" />
    ),
  },
  {
    id: 'status',
    accessorFn: (c) => c.latest_appeal?.status ?? 'none',
    header: 'Status',
    meta: { label: 'Status' },
    cell: ({ row }) => {
      const appeal = row.original.latest_appeal;
      if (!appeal) return <Badge tone="info">Ready to draft</Badge>;
      const tone =
        appeal.status === 'signed' || appeal.status === 'exported'
          ? 'navy'
          : appeal.status === 'in_review'
            ? 'info'
            : 'warning';
      return <Badge tone={tone}>{APPEAL_STATUS[appeal.status]}</Badge>;
    },
  },
  {
    id: 'updated',
    accessorFn: (c) => c.updated_at ?? '',
    header: 'Updated',
    meta: { label: 'Updated', align: 'right' },
    cell: ({ row }) => (
      <span className="text-ink-subtle">{formatRelative(row.original.updated_at)}</span>
    ),
  },
];

export default function AppealsPage() {
  const claims = useClaims({});
  const navigate = useNavigate();
  const rows = useMemo(
    () =>
      (claims.data?.items ?? []).filter(
        (c) =>
          c.latest_appeal !== null ||
          (c.mode !== 'pre_submission' && (c.totals?.recoverable_on_appeal ?? 0) > 0),
      ),
    [claims.data],
  );
  const signed = rows.filter(
    (r) => r.latest_appeal?.status === 'signed' || r.latest_appeal?.status === 'exported',
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title="Appeals"
        description={`Every appeal on the desk. ${String(signed.length)} signed; nothing is sent before a named reviewer signs it.`}
      />
      <Card className="overflow-hidden">
        {claims.isError ? (
          <ProblemAlert
            error={claims.error}
            onRetry={() => void claims.refetch()}
            className="m-4"
          />
        ) : claims.isPending ? (
          <TableSkeleton />
        ) : rows.length === 0 ? (
          <EmptyState
            className="m-4"
            icon={<Scale aria-hidden />}
            title="No appeals yet"
            description="When an audit finds an insurer deduction or rejection the rules dispute, the claim appears here, ready to draft."
            action={
              <Button asChild variant="secondary">
                <Link to="/worklist">Go to the worklist</Link>
              </Button>
            }
          />
        ) : (
          <DataTable
            caption="Appeals"
            data={rows}
            columns={columns}
            getRowId={(c) => c.claim_id}
            initialSorting={[{ id: 'updated', desc: true }]}
            onOpen={(c) => {
              void navigate(`/claims/${c.claim_id}/appeal`);
            }}
          />
        )}
      </Card>
    </div>
  );
}
