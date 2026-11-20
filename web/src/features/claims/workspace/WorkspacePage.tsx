/**
 * The claim workspace: money at stake, the findings and the bill beside the source documents.
 * While an audit runs it streams progress; afterwards every tab works from the persisted claim.
 */
import { FileQuestion, PanelLeftClose, PanelLeftOpen, Play } from 'lucide-react';
import { useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router';
import { toast } from 'sonner';

import { ApiProblem } from '@/api/client';
import { useClaim, useDocuments, useStartRun } from '@/api/queries';
import type { BillLine, ClaimRecord } from '@/api/types';
import { useRunEvents } from '@/api/useRunEvents';
import { EmptyState, ProblemAlert } from '@/components/states';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/overlays';
import { Card, Skeleton } from '@/components/ui/primitives';
import { ActivityTab } from '@/features/claims/workspace/ActivityTab';
import { BillLinesTab } from '@/features/claims/workspace/BillLinesTab';
import { type DocumentFocus, DocumentViewer } from '@/features/claims/workspace/DocumentViewer';
import { FlagsTab } from '@/features/claims/workspace/FlagsTab';
import { LiveRun } from '@/features/claims/workspace/LiveRun';
import { MoneyBand } from '@/features/claims/workspace/MoneyBand';
import { PolicyTab } from '@/features/claims/workspace/PolicyTab';
import { WorkspaceHeader } from '@/features/claims/workspace/WorkspaceHeader';

const FAILURE: Record<string, string> = {
  'replay-miss':
    'These documents have no recorded responses, and this deployment serves recordings only. Use the demo cases, or switch the AI to live mode.',
  'budget-exceeded':
    'Today’s AI budget is used up. Live audits resume tomorrow; replay mode still works.',
  'llm-rate-limited': 'The AI service is busy. Re-run the audit in a minute.',
  'facts-incomplete':
    'Some required details could not be read from the documents. Check the uploads and re-run.',
};

function activeRunId(claim: ClaimRecord | undefined, fromUrl: string | null): string | null {
  if (fromUrl) return fromUrl;
  if (claim?.status !== 'processing') return null;
  return claim.runs.at(-1)?.run_id ?? null;
}

export default function WorkspacePage() {
  const { claimId = '' } = useParams();
  const [params, setParams] = useSearchParams();
  const claim = useClaim(claimId);
  const documents = useDocuments(claimId);
  const startRun = useStartRun();
  const runId = activeRunId(claim.data, params.get('run'));
  const stream = useRunEvents(claimId, runId);
  const [focus, setFocus] = useState<DocumentFocus | null>(null);
  const [tab, setTab] = useState('flags');
  // The bill table needs the full width; the documents come back when a line is shown on the bill.
  const [docsOpen, setDocsOpen] = useState(true);

  function changeTab(next: string) {
    setTab(next);
    if (next === 'lines') setDocsOpen(false);
  }

  const finished = stream.state === 'completed' || stream.state === 'failed';
  const live = runId !== null && !finished;

  function rerun() {
    startRun.mutate(claimId, {
      onSuccess: (run) => {
        setParams({ run: run.run_id }, { replace: true });
      },
      onError: (e) =>
        toast.error('Could not start the audit', {
          description: e instanceof ApiProblem ? e.detail : undefined,
        }),
    });
  }

  function showLine(line: BillLine) {
    setDocsOpen(true);
    setFocus({
      documentType: 'itemised_bill',
      page: line.source_page ?? 1,
      query: line.description,
      nonce: Date.now(),
    });
  }

  if (claim.isPending) {
    return (
      <div className="space-y-4" role="status" aria-label="Loading claim">
        <Skeleton className="h-8 w-80" />
        <Skeleton className="h-28" />
        <div className="grid grid-cols-2 gap-4">
          <Skeleton className="h-[32rem]" />
          <Skeleton className="h-[32rem]" />
        </div>
      </div>
    );
  }
  if (claim.isError) {
    if (claim.error instanceof ApiProblem && claim.error.status === 404) {
      return (
        <EmptyState
          icon={<FileQuestion aria-hidden />}
          title="Claim not found"
          description="It may belong to another hospital, or the link is out of date."
          action={
            <Button asChild>
              <Link to="/worklist">Back to the worklist</Link>
            </Button>
          }
        />
      );
    }
    return <ProblemAlert error={claim.error} onRetry={() => void claim.refetch()} />;
  }

  const data = claim.data;
  const audited = data.audit && data.facts && !live;

  return (
    <div className="space-y-5">
      <WorkspaceHeader claim={data} onRerun={rerun} rerunning={startRun.isPending} />

      {live ? <LiveRun stream={stream} /> : null}

      {!live && data.status === 'failed' ? (
        <ProblemAlert
          error={
            new ApiProblem(
              0,
              stream.error ?? 'run-failed',
              'The audit stopped',
              FAILURE[stream.error ?? data.runs.at(-1)?.error ?? ''] ??
                'Something went wrong while reading the documents. Re-run the audit; if it fails again, share the claim ID with support.',
              null,
            )
          }
          onRetry={rerun}
        />
      ) : null}

      {!live && !data.audit && (data.status === 'documents_uploaded' || data.status === 'draft') ? (
        <EmptyState
          icon={<Play aria-hidden />}
          title="Ready to audit"
          description={
            data.consent
              ? `${String(documents.data?.length ?? 0)} documents uploaded. Run the audit to see every flag with its ₹ impact.`
              : 'Record the patient’s consent before the documents are processed.'
          }
          action={
            data.consent ? (
              <Button onClick={rerun} loading={startRun.isPending}>
                Run audit
              </Button>
            ) : (
              <Button asChild>
                <Link to="/audits/new">Start a new audit</Link>
              </Button>
            )
          }
        />
      ) : null}

      {audited && data.audit ? (
        <>
          <MoneyBand audit={data.audit} mode={data.mode} />
          <div
            className={
              docsOpen
                ? 'grid min-h-0 gap-4 xl:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]'
                : 'grid min-h-0 gap-4'
            }
          >
            <Card
              className={
                docsOpen
                  ? 'flex h-[calc(100vh-7rem)] min-h-[36rem] flex-col overflow-hidden xl:sticky xl:top-20'
                  : 'hidden'
              }
            >
              {documents.isPending ? (
                <Skeleton className="m-4 flex-1" />
              ) : documents.isError ? (
                <ProblemAlert error={documents.error} className="m-4" />
              ) : (
                <DocumentViewer claimId={claimId} documents={documents.data} focus={focus} />
              )}
            </Card>
            <Card className="min-w-0 overflow-hidden">
              <Tabs value={tab} onValueChange={changeTab}>
                <div className="flex items-center border-b border-border pr-2">
                  <TabsList aria-label="Claim details" className="flex-1 border-b-0">
                    <TabsTrigger value="flags">
                      Flags{' '}
                      <span className="rounded-full bg-sunken px-1.5 text-xs tabular-nums">
                        {data.audit.flags.length}
                      </span>
                    </TabsTrigger>
                    <TabsTrigger value="lines">
                      Bill lines
                      {data.issues.length ? (
                        <span
                          className="size-1.5 rounded-full bg-warning"
                          aria-label="needs confirmation"
                        />
                      ) : null}
                    </TabsTrigger>
                    <TabsTrigger value="policy">Policy terms</TabsTrigger>
                    <TabsTrigger value="activity">Activity</TabsTrigger>
                  </TabsList>
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-pressed={docsOpen}
                    onClick={() => {
                      setDocsOpen(!docsOpen);
                    }}
                  >
                    {docsOpen ? <PanelLeftClose aria-hidden /> : <PanelLeftOpen aria-hidden />}
                    {docsOpen ? 'Hide documents' : 'Show documents'}
                  </Button>
                </div>
                <TabsContent value="flags">
                  <FlagsTab claim={data} onLine={showLine} />
                </TabsContent>
                <TabsContent value="lines">
                  <BillLinesTab claim={data} onLine={showLine} />
                </TabsContent>
                <TabsContent value="policy">
                  <PolicyTab claim={data} />
                </TabsContent>
                <TabsContent value="activity">
                  <ActivityTab claimId={claimId} />
                </TabsContent>
              </Tabs>
            </Card>
          </div>
        </>
      ) : null}
    </div>
  );
}
