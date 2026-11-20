/**
 * Appeal editor: choose the forum and draft, then edit section by section (amounts locked),
 * submit for review, and sign. Nothing can be exported until a named reviewer signs.
 * E toggles editing; S opens Review & sign.
 */
import { FileSignature, Pencil, Save, Scale, Send, ShieldCheck, X } from 'lucide-react';
import { useCallback, useState } from 'react';
import { Link, useParams } from 'react-router';
import { toast } from 'sonner';

import { ApiProblem } from '@/api/client';
import {
  useAppeals,
  useCitations,
  useClaim,
  useDraftAppeal,
  useEditAppeal,
  useSubmitAppeal,
} from '@/api/queries';
import type { AppealEdit, AppealVersion } from '@/api/types';
import { WarningNote } from '@/components/domain';
import { EmptyState, PageHeader, ProblemAlert } from '@/components/states';
import { Button } from '@/components/ui/button';
import { Badge, Card, Kbd, Skeleton } from '@/components/ui/primitives';
import { useShortcut } from '@/lib/hooks';
import { APPEAL_STATUS, FORUM } from '@/lib/labels';
import { AppealRail, verifyRefs } from '@/features/appeal/AppealRail';
import { AppealSections, type AppealDraftState, draftFrom } from '@/features/appeal/AppealSections';
import { placeholderOptions } from '@/features/appeal/appealText';
import { ForumPicker } from '@/features/appeal/ForumPicker';
import { SignDialog } from '@/features/appeal/SignDialog';
import { canAppeal } from '@/features/claims/workspace/WorkspaceHeader';

function changes(appeal: AppealVersion, draft: AppealDraftState): AppealEdit {
  const base = draftFrom(appeal);
  const body: AppealEdit = {};
  if (draft.subject !== base.subject) body.subject = draft.subject;
  if (draft.facts !== base.facts) body.facts = draft.facts;
  if (draft.relief !== base.relief) body.relief = draft.relief;
  const args = Object.entries(draft.arguments).filter(([id, text]) => text !== base.arguments[id]);
  if (args.length) body.arguments = args.map(([flag_id, argument]) => ({ flag_id, argument }));
  return body;
}

export default function AppealEditorPage() {
  const { claimId = '' } = useParams();
  const claim = useClaim(claimId);
  const appeals = useAppeals(claimId);
  const { data: registry } = useCitations();
  const draftAppeal = useDraftAppeal(claimId);
  const edit = useEditAppeal(claimId);
  const submit = useSubmitAppeal(claimId);
  const [viewing, setViewing] = useState<number | null>(null);
  const [draft, setDraft] = useState<AppealDraftState | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [acknowledged, setAcknowledged] = useState(false);
  const [signOpen, setSignOpen] = useState(false);

  const versions = appeals.data ?? [];
  const latest = versions.at(-1);
  const shown = versions.find((v) => v.version === viewing) ?? latest;
  const isLatest = shown?.version === latest?.version;
  const editing = draft !== null && isLatest;

  const startEdit = useCallback(() => {
    if (shown && isLatest && shown.status !== 'exported') {
      setDraft(draftFrom(shown));
      setErrors([]);
    }
  }, [shown, isLatest]);
  const openSign = useCallback(() => {
    if (shown?.status === 'in_review' || shown?.signature) setSignOpen(true);
  }, [shown]);
  useShortcut('e', startEdit, !editing && Boolean(shown));
  useShortcut('s', openSign, !editing && Boolean(shown));

  if (claim.isPending || appeals.isPending)
    return (
      <div className="space-y-4" role="status" aria-label="Loading appeal">
        <Skeleton className="h-8 w-80" />
        <Skeleton className="h-[36rem]" />
      </div>
    );
  if (claim.isError)
    return <ProblemAlert error={claim.error} onRetry={() => void claim.refetch()} />;
  if (appeals.isError)
    return <ProblemAlert error={appeals.error} onRetry={() => void appeals.refetch()} />;

  const data = claim.data;
  const clauses = data.facts?.policy.clauses ?? [];
  const header = (
    <PageHeader
      eyebrow={
        <>
          <Link to="/worklist" className="hover:underline">
            Worklist
          </Link>{' '}
          /{' '}
          <Link to={`/claims/${claimId}`} className="font-mono hover:underline">
            {claimId}
          </Link>{' '}
          / Appeal
        </>
      }
      title={shown ? `Appeal to ${FORUM[shown.forum].label}` : 'Draft an appeal'}
      description={
        shown
          ? `Version ${String(shown.version)} · ${String(shown.content.items.length)} disputed ${shown.content.items.length === 1 ? 'item' : 'items'}`
          : 'Arzi drafts the arguments; disputed items, amounts and relief come from the rules engine.'
      }
    />
  );

  if (!shown) {
    return (
      <div className="space-y-6">
        {header}
        {canAppeal(data) ? (
          <Card className="p-6">
            {draftAppeal.isError ? (
              <ProblemAlert error={draftAppeal.error} className="mb-4" />
            ) : null}
            <ForumPicker
              claimId={claimId}
              drafting={draftAppeal.isPending}
              onDraft={(forum, complaint) => {
                draftAppeal.mutate(
                  { forum, gro_complaint: complaint },
                  {
                    onSuccess: () =>
                      toast.success('Appeal drafted', {
                        description: 'Review each section, then submit it for review.',
                      }),
                  },
                );
              }}
            />
          </Card>
        ) : (
          <EmptyState
            icon={<Scale aria-hidden />}
            title="Nothing to appeal"
            description="The audit found no insurer decision to dispute on this claim."
            action={
              <Button asChild variant="secondary">
                <Link to={`/claims/${claimId}`}>Back to the claim</Link>
              </Button>
            }
          />
        )}
      </div>
    );
  }

  const needsAck = verifyRefs(shown, registry).length > 0 && !acknowledged;
  const signed = shown.signature;

  function save() {
    if (!shown || !draft) return;
    const body = changes(shown, draft);
    if (Object.keys(body).length === 0) {
      setDraft(null);
      return;
    }
    edit.mutate(
      { version: shown.version, body },
      {
        onSuccess: (next) => {
          setDraft(null);
          setErrors([]);
          setViewing(next.version);
          toast.success(`Saved as version ${String(next.version)}`);
        },
        onError: (e) => {
          setErrors(e instanceof ApiProblem ? [e.detail] : []);
        },
      },
    );
  }

  return (
    <div className="space-y-5">
      {header}
      <div
        className={
          signed
            ? 'rounded-lg border border-success-border bg-success-bg px-4 py-3 text-success'
            : shown.status === 'in_review'
              ? 'rounded-lg border border-info-border bg-info-bg px-4 py-3 text-info'
              : 'rounded-lg border border-warning-border bg-warning-bg px-4 py-3 text-warning'
        }
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="flex items-center gap-2 font-medium">
            {signed ? (
              <ShieldCheck className="size-4" aria-hidden />
            ) : (
              <FileSignature className="size-4" aria-hidden />
            )}
            {signed
              ? `Signed by ${signed.reviewer_name}, ${signed.reviewer_role}`
              : APPEAL_STATUS[shown.status]}
            {!isLatest ? <Badge>Older version, read only</Badge> : null}
          </p>
          {signed ? (
            <span className="font-mono text-xs break-all">
              SHA-256 {signed.content_sha256.slice(0, 16)}…
            </span>
          ) : (
            <span className="text-xs">
              Arzi is decision support: a named reviewer must sign before export.
            </span>
          )}
        </div>
      </div>
      {shown.drafting === 'needs_review' ? (
        <WarningNote>
          Part of the draft did not pass Arzi’s checks ({shown.violations.join('; ')}). Edit the
          highlighted sections before submitting.
        </WarningNote>
      ) : null}
      {shown.drafting === 'unavailable' ? (
        <WarningNote>
          The AppealDrafter was not available, so the arguments are empty. Write them, then submit
          for review.
        </WarningNote>
      ) : null}

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_20rem]">
        <Card>
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-5 py-3">
            <p className="text-xs text-ink-subtle">
              {editing ? (
                'Amounts stay locked: insert them from the menu, never type them.'
              ) : (
                <>
                  Press <Kbd>E</Kbd> to edit
                  {shown.status === 'in_review' ? (
                    <>
                      , <Kbd>S</Kbd> to sign
                    </>
                  ) : null}
                </>
              )}
            </p>
            {isLatest ? (
              <div className="flex flex-wrap gap-2">
                {editing ? (
                  <>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        setDraft(null);
                        setErrors([]);
                      }}
                    >
                      <X aria-hidden />
                      Cancel
                    </Button>
                    <Button size="sm" onClick={save} loading={edit.isPending}>
                      {edit.isPending ? null : <Save aria-hidden />}Save as new version
                    </Button>
                  </>
                ) : (
                  <>
                    {shown.status !== 'exported' ? (
                      <Button variant="secondary" size="sm" onClick={startEdit}>
                        <Pencil aria-hidden />
                        Edit
                      </Button>
                    ) : null}
                    {shown.status === 'draft' ? (
                      <Button
                        size="sm"
                        disabled={needsAck}
                        loading={submit.isPending}
                        onClick={() => {
                          submit.mutate(shown.version, {
                            onSuccess: () => toast.success('Submitted for review'),
                            onError: (e) =>
                              toast.error('Not ready for review', {
                                description: e instanceof ApiProblem ? e.detail : undefined,
                              }),
                          });
                        }}
                      >
                        {submit.isPending ? null : <Send aria-hidden />}Submit for review
                      </Button>
                    ) : null}
                    {shown.status === 'in_review' ? (
                      <Button
                        variant="accent"
                        size="sm"
                        disabled={needsAck}
                        onClick={() => {
                          setSignOpen(true);
                        }}
                      >
                        <FileSignature aria-hidden />
                        Review and sign
                      </Button>
                    ) : null}
                    {signed ? (
                      <Button
                        size="sm"
                        onClick={() => {
                          setSignOpen(true);
                        }}
                      >
                        <ShieldCheck aria-hidden />
                        Export
                      </Button>
                    ) : null}
                  </>
                )}
              </div>
            ) : null}
          </div>
          <div className="p-5">
            {errors.length ? (
              <ProblemAlert
                error={
                  new ApiProblem(
                    422,
                    'appeal-guardrail',
                    'These edits break the appeal rules',
                    errors.join(' '),
                    null,
                  )
                }
                className="mb-4"
              />
            ) : null}
            {needsAck && (shown.status === 'draft' || shown.status === 'in_review') && !editing ? (
              <p className="mb-4 text-xs text-warning">
                Acknowledge the references marked Verify (right) to continue.
              </p>
            ) : null}
            <AppealSections
              appeal={shown}
              draft={draft ?? draftFrom(shown)}
              editing={editing}
              onChange={setDraft}
              options={placeholderOptions(data)}
              clauses={clauses}
              errors={errors}
            />
          </div>
        </Card>
        <AppealRail
          appeal={shown}
          versions={versions}
          viewing={shown.version}
          onView={(v) => {
            setViewing(v);
            setDraft(null);
          }}
          clauses={clauses}
          acknowledged={acknowledged}
          onAcknowledge={setAcknowledged}
        />
      </div>
      <SignDialog claimId={claimId} appeal={shown} open={signOpen} onOpenChange={setSignOpen} />
    </div>
  );
}
