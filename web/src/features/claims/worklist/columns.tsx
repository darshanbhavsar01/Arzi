/** Worklist columns. Amounts are engine totals; the patient is the redaction pseudonym. */
import type { ColumnDef } from '@tanstack/react-table';
import { Timer } from 'lucide-react';

import type { ClaimSummary } from '@/api/types';
import type { ColumnMeta } from '@/components/DataTable';
import { Money, SeveritySummary, StatusPill } from '@/components/domain';
import { Tooltip } from '@/components/ui/overlays';
import { cn } from '@/lib/cn';
import { formatRelative } from '@/lib/format';
import { MODE } from '@/lib/labels';

const DISCHARGE_TARGET_MS = 3 * 60 * 60 * 1000;

/** Countdown to the IRDAI 3-hour discharge-authorisation target, for claims not yet filed. */
export function DischargeClock({ claim, now }: { claim: ClaimSummary; now: number }) {
  if (claim.mode !== 'pre_submission' || !claim.created_at) {
    return <span className="text-ink-subtle">—</span>;
  }
  const left = new Date(claim.created_at).getTime() + DISCHARGE_TARGET_MS - now;
  const minutes = Math.round(Math.abs(left) / 60_000);
  const text =
    minutes >= 60
      ? `${String(Math.floor(minutes / 60))} h ${String(minutes % 60)} m`
      : `${String(minutes)} m`;
  const overdue = left < 0;
  return (
    <Tooltip
      content={
        <>
          IRDAI expects the insurer to decide discharge authorisation within 3 hours of the
          hospital’s request (IRDAI_CASHLESS_TAT). <strong>Verify before filing:</strong> the
          paragraph number is still being confirmed.
        </>
      }
    >
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
        }}
        className={cn(
          'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium whitespace-nowrap tabular-nums',
          overdue
            ? 'border-danger-border bg-danger-bg text-danger'
            : left < 30 * 60_000
              ? 'border-warning-border bg-warning-bg text-warning'
              : 'border-border bg-sunken text-ink-muted',
        )}
      >
        <Timer className="size-3" aria-hidden />
        {overdue ? `${text} over` : `${text} left`}
      </button>
    </Tooltip>
  );
}

const right: ColumnMeta = { align: 'right' };

export function worklistColumns(now: number): ColumnDef<ClaimSummary>[] {
  return [
    {
      id: 'claim',
      accessorFn: (c) => c.claim_id,
      header: 'Claim',
      enableHiding: false,
      meta: { label: 'Claim' },
      cell: ({ row }) => (
        <span className="font-mono text-[0.8125rem] font-medium whitespace-nowrap text-navy">
          {row.original.claim_id}
        </span>
      ),
    },
    {
      id: 'patient',
      accessorFn: (c) => c.patient ?? '',
      header: 'Patient',
      meta: { label: 'Patient' },
      cell: ({ row }) =>
        row.original.patient ? (
          <span className="font-mono text-[0.8125rem]">{row.original.patient}</span>
        ) : (
          <span className="text-ink-subtle">Not audited</span>
        ),
    },
    {
      id: 'insurer',
      accessorFn: (c) => c.insurer ?? '',
      header: 'Insurer / TPA',
      meta: { label: 'Insurer / TPA' },
      cell: ({ getValue }) => (
        <span className="block max-w-44 truncate" title={String(getValue())}>
          {String(getValue()) || '—'}
        </span>
      ),
    },
    {
      id: 'mode',
      accessorFn: (c) => MODE[c.mode].short,
      header: 'Mode',
      meta: { label: 'Mode' },
      cell: ({ getValue }) => <span className="whitespace-nowrap">{String(getValue())}</span>,
    },
    {
      id: 'billed',
      accessorFn: (c) => c.totals?.billed ?? -1,
      header: 'Billed',
      meta: { ...right, label: 'Billed' },
      cell: ({ row }) => (row.original.totals ? <Money paise={row.original.totals.billed} /> : '—'),
    },
    {
      id: 'value',
      accessorFn: (c) =>
        c.mode === 'pre_submission'
          ? (c.totals?.at_risk ?? -1)
          : (c.totals?.recoverable_on_appeal ?? -1),
      header: 'At risk / recoverable',
      meta: { ...right, label: 'At risk / recoverable' },
      cell: ({ row }) => {
        const t = row.original.totals;
        if (!t) return '—';
        return row.original.mode === 'pre_submission' ? (
          <Money paise={t.at_risk} tone={t.at_risk ? 'risk' : 'muted'} />
        ) : (
          <Money
            paise={t.recoverable_on_appeal}
            tone={t.recoverable_on_appeal ? 'recover' : 'muted'}
          />
        );
      },
    },
    {
      id: 'flags',
      accessorFn: (c) => c.flag_count,
      header: 'Flags',
      meta: { label: 'Flags' },
      cell: ({ row }) => <SeveritySummary severities={row.original.severities} />,
    },
    {
      id: 'clock',
      accessorFn: (c) => c.created_at ?? '',
      header: 'IRDAI clock',
      enableSorting: false,
      meta: { label: 'IRDAI clock' },
      cell: ({ row }) => <DischargeClock claim={row.original} now={now} />,
    },
    {
      id: 'status',
      accessorFn: (c) => c.status,
      header: 'Status',
      meta: { label: 'Status' },
      cell: ({ row }) => <StatusPill status={row.original.status} />,
    },
    {
      id: 'updated',
      accessorFn: (c) => c.updated_at ?? '',
      header: 'Updated',
      meta: { ...right, label: 'Updated' },
      cell: ({ row }) => (
        <span className="text-ink-subtle">{formatRelative(row.original.updated_at, now)}</span>
      ),
    },
  ];
}
