/** The worklist: today's claims, what is at stake, and what needs a person next. */
import { Clock4, FilePlus2, Inbox, IndianRupee, Search, Sparkles, TrendingUp } from 'lucide-react';
import { useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router';
import { toast } from 'sonner';

import { useClaims, useLoadDemo, useWorkspace } from '@/api/queries';
import type { ClaimMode, ClaimSummary } from '@/api/types';
import { DataTable } from '@/components/DataTable';
import { KpiTile } from '@/components/domain';
import { EmptyState, PageHeader, ProblemAlert, TableSkeleton } from '@/components/states';
import { Button } from '@/components/ui/button';
import { Card, Input, Select } from '@/components/ui/primitives';
import { cn } from '@/lib/cn';
import { formatDuration, formatMoneyCompact } from '@/lib/format';
import { useDebounced, useNow } from '@/lib/hooks';
import { MODE } from '@/lib/labels';
import { worklistColumns } from '@/features/claims/worklist/columns';

const VIEWS = [
  { id: 'all', label: 'All claims', match: () => true },
  {
    id: 'discharge',
    label: 'Discharge today',
    match: (c: ClaimSummary) => c.mode === 'pre_submission',
  },
  {
    id: 'review',
    label: 'Needs review',
    match: (c: ClaimSummary) =>
      c.needs_confirmation > 0 || c.status === 'failed' || c.status === 'documents_uploaded',
  },
  {
    id: 'appeals',
    label: 'Appeals',
    match: (c: ClaimSummary) => c.mode !== 'pre_submission',
  },
] as const;

type ViewId = (typeof VIEWS)[number]['id'];

function median(values: number[]): number | null {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2
    ? (sorted[mid] ?? null)
    : ((sorted[mid - 1] ?? 0) + (sorted[mid] ?? 0)) / 2;
}

export default function WorklistPage() {
  const [view, setView] = useState<ViewId>('all');
  const [search, setSearch] = useState('');
  const [mode, setMode] = useState<ClaimMode | ''>('');
  const [insurer, setInsurer] = useState('');
  const q = useDebounced(search.trim());
  const claims = useClaims({ q: q || undefined, mode: mode || undefined });
  const { data: workspace } = useWorkspace();
  const demo = useLoadDemo();
  const navigate = useNavigate();
  const now = useNow();
  const columns = useMemo(() => worklistColumns(now), [now]);

  const items = useMemo(() => claims.data?.items ?? [], [claims.data]);
  const insurers = useMemo(
    () => [...new Set(items.map((c) => c.insurer).filter(Boolean))] as string[],
    [items],
  );
  const scoped = items.filter((c) => !insurer || c.insurer === insurer);
  const current = VIEWS.find((v) => v.id === view) ?? VIEWS[0];
  const rows = scoped.filter(current.match);

  const atRisk = scoped
    .filter((c) => c.mode === 'pre_submission')
    .reduce((s, c) => s + (c.totals?.at_risk ?? 0), 0);
  const recoverable = scoped.reduce((s, c) => s + (c.totals?.recoverable_on_appeal ?? 0), 0);
  const timing = median(scoped.map((c) => c.audit_seconds).filter((v): v is number => v !== null));
  const filtering = Boolean(q || mode || insurer);

  function loadDemo() {
    demo.mutate(undefined, {
      onSuccess: (loaded) => {
        toast.success('Demo cases loaded', {
          description: `${String(loaded.length)} synthetic claims are being audited now.`,
        });
      },
      onError: () => toast.error('Could not load the demo cases'),
    });
  }

  const demoButton = workspace?.demo_cases_available ? (
    <Button variant="secondary" onClick={loadDemo} loading={demo.isPending}>
      {demo.isPending ? null : <Sparkles aria-hidden />}
      Load demo cases
    </Button>
  ) : null;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Worklist"
        description="Every claim the desk is working on: what is at risk before filing and what an appeal can recover."
        actions={
          <>
            {demoButton}
            <Button asChild>
              <Link to="/audits/new">
                <FilePlus2 aria-hidden />
                New audit
              </Link>
            </Button>
          </>
        }
      />

      <section aria-label="Key figures" className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <KpiTile
          label="Claims on the desk"
          icon={<Inbox aria-hidden />}
          value={scoped.length}
          hint={`${String(scoped.filter((c) => c.status === 'audited').length)} audited`}
        />
        <KpiTile
          label="At risk before filing"
          icon={<IndianRupee aria-hidden />}
          tone="risk"
          value={formatMoneyCompact(atRisk)}
          hint="Likely deductions on unfiled claims"
        />
        <KpiTile
          label="Recoverable on appeal"
          icon={<TrendingUp aria-hidden />}
          tone="recover"
          value={formatMoneyCompact(recoverable)}
          hint="Insurer decisions the rules dispute"
        />
        <KpiTile
          label="Median audit time"
          icon={<Clock4 aria-hidden />}
          value={formatDuration(timing)}
          hint="Upload to flags, end to end"
        />
      </section>

      <Card className="overflow-hidden">
        <div
          className="flex items-center gap-1 border-b border-border px-4"
          role="group"
          aria-label="Saved views"
        >
          {VIEWS.map((v) => {
            const count = scoped.filter(v.match).length;
            return (
              <button
                key={v.id}
                type="button"
                aria-pressed={view === v.id}
                onClick={() => {
                  setView(v.id);
                }}
                className={cn(
                  '-mb-px inline-flex h-11 items-center gap-2 border-b-2 px-3 text-sm font-medium',
                  view === v.id
                    ? 'border-accent text-ink'
                    : 'border-transparent text-ink-muted hover:text-ink',
                )}
              >
                {v.label}
                <span className="rounded-full bg-sunken px-1.5 text-xs tabular-nums text-ink-muted">
                  {count}
                </span>
              </button>
            );
          })}
        </div>

        {claims.isError ? (
          <ProblemAlert
            error={claims.error}
            onRetry={() => void claims.refetch()}
            className="m-4"
          />
        ) : claims.isPending ? (
          <TableSkeleton />
        ) : items.length === 0 && !filtering ? (
          <EmptyState
            className="m-4"
            icon={<Inbox aria-hidden />}
            title="No claims yet"
            description="Start an audit by uploading a policy, the itemised bill and the discharge summary, or load three synthetic demo cases to see Arzi at work."
            action={
              <>
                {demoButton}
                <Button asChild>
                  <Link to="/audits/new">
                    <FilePlus2 aria-hidden />
                    New audit
                  </Link>
                </Button>
              </>
            }
          />
        ) : (
          <DataTable
            caption="Claims on the desk"
            data={rows}
            columns={columns}
            getRowId={(c) => c.claim_id}
            initialSorting={[{ id: 'updated', desc: true }]}
            onOpen={(c) => {
              void navigate(`/claims/${c.claim_id}`);
            }}
            toolbar={
              <>
                <div className="relative w-64">
                  <label htmlFor="worklist-search" className="sr-only">
                    Search claims
                  </label>
                  <Search
                    className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-ink-subtle"
                    aria-hidden
                  />
                  <Input
                    id="worklist-search"
                    type="search"
                    value={search}
                    onChange={(e) => {
                      setSearch(e.target.value);
                    }}
                    placeholder="Claim ID or insurer"
                    className="pl-8"
                  />
                </div>
                <Select
                  aria-label="Mode"
                  value={mode}
                  onChange={(e) => {
                    setMode(e.target.value as ClaimMode | '');
                  }}
                  className="w-48"
                >
                  <option value="">All modes</option>
                  {(Object.keys(MODE) as ClaimMode[]).map((m) => (
                    <option key={m} value={m}>
                      {MODE[m].label}
                    </option>
                  ))}
                </Select>
                <Select
                  aria-label="Insurer"
                  value={insurer}
                  onChange={(e) => {
                    setInsurer(e.target.value);
                  }}
                  className="w-60"
                >
                  <option value="">All insurers</option>
                  {insurers.map((i) => (
                    <option key={i} value={i}>
                      {i}
                    </option>
                  ))}
                </Select>
              </>
            }
          />
        )}
        {!claims.isPending &&
        !claims.isError &&
        rows.length === 0 &&
        (items.length > 0 || filtering) ? (
          <p className="px-4 py-10 text-center text-ink-muted">
            No claims match this view and filters.
          </p>
        ) : null}
      </Card>
    </div>
  );
}
