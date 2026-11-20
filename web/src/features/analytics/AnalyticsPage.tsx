/** Desk analytics: what the audits found, what is being appealed and what reviewers signed. */
import { BarChart3, CheckCircle2, Clock4, FileSearch, IndianRupee } from 'lucide-react';
import { useMemo } from 'react';
import { Link } from 'react-router';

import { useClaims } from '@/api/queries';
import { KpiTile } from '@/components/domain';
import { EmptyState, PageHeader, ProblemAlert } from '@/components/states';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/primitives';
import { formatDuration, formatMoneyCompact } from '@/lib/format';
import { MODE } from '@/lib/labels';

import { summarise } from './aggregate';
import { BarList } from './BarList';

export default function AnalyticsPage() {
  const claims = useClaims({});
  const stats = useMemo(
    () => summarise(claims.data?.items ?? [], (m) => MODE[m].short),
    [claims.data],
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title="Analytics"
        description="Computed from the audits on this desk. Every rupee figure comes from the rules engine."
      />
      {claims.isError ? (
        <ProblemAlert error={claims.error} onRetry={() => void claims.refetch()} />
      ) : claims.isPending ? (
        <div className="space-y-4" role="status" aria-label="Loading analytics">
          <div className="grid grid-cols-4 gap-4">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-24" />
            ))}
          </div>
          <Skeleton className="h-64" />
        </div>
      ) : stats.audited === 0 ? (
        <EmptyState
          icon={<BarChart3 aria-hidden />}
          title="No audits to analyse yet"
          description="Run an audit or load the demo cases and the numbers appear here."
          action={
            <Button asChild variant="secondary">
              <Link to="/worklist">Go to the worklist</Link>
            </Button>
          }
        />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
            <KpiTile
              label="Claims audited"
              icon={<FileSearch aria-hidden />}
              value={stats.audited}
            />
            <KpiTile
              label="At risk found"
              icon={<IndianRupee aria-hidden />}
              tone="risk"
              value={formatMoneyCompact(stats.atRisk)}
            />
            <KpiTile
              label="Recoverable on appeal"
              icon={<CheckCircle2 aria-hidden />}
              tone="recover"
              value={formatMoneyCompact(stats.recoverable)}
              hint={`${String(stats.signed)} appeal${stats.signed === 1 ? '' : 's'} signed`}
            />
            <KpiTile
              label="Average audit time"
              icon={<Clock4 aria-hidden />}
              value={formatDuration(stats.avgAuditSeconds)}
            />
          </div>
          <div className="grid gap-4 xl:grid-cols-2">
            <BarList title="₹ at risk by insurer" bars={stats.byInsurer} tone="accent" />
            <BarList title="₹ at risk by decision stage" bars={stats.byMode} />
            <BarList title="₹ at risk by week (claim created)" bars={stats.weekly} />
            <BarList title="Recovery funnel (₹)" bars={stats.funnel} tone="success" />
          </div>
        </>
      )}
    </div>
  );
}
