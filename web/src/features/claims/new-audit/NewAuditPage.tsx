/**
 * New audit in three steps: what kind of claim → its documents → consent and run. Files stay in
 * the browser until "Run audit", so nothing is stored for an abandoned audit.
 */
import { ArrowLeft, ArrowRight, FileCheck2, FileWarning, FileX2, Play } from 'lucide-react';
import { useState } from 'react';
import { useNavigate } from 'react-router';

import { ApiProblem } from '@/api/client';
import { useCreateClaim, useRecordConsent, useStartRun } from '@/api/queries';
import type { ClaimMode, DocType } from '@/api/types';
import { uploadDocument } from '@/api/upload';
import { PageHeader, ProblemAlert } from '@/components/states';
import { Button } from '@/components/ui/button';
import { Card, Checkbox, Input, Label, Select } from '@/components/ui/primitives';
import { cn } from '@/lib/cn';
import { MODE } from '@/lib/labels';
import { FilePicker } from '@/features/claims/new-audit/FilePicker';
import {
  coverage,
  type PickedFile,
  rejectReason,
  requirements,
} from '@/features/claims/new-audit/files';

const STEPS = ['Claim type', 'Documents', 'Consent and run'] as const;
const MODE_ICON = {
  pre_submission: FileCheck2,
  post_deduction: FileWarning,
  post_rejection: FileX2,
};
const MODE_BLURB: Record<ClaimMode, string> = {
  pre_submission:
    'Before filing: find every likely deduction, the ₹ at risk and the fix while the patient is still admitted.',
  post_deduction:
    'The insurer paid less than billed: check each deduction against IRDAI rules and the policy.',
  post_rejection: 'The insurer rejected the claim: test the grounds and prepare an appeal.',
};

export default function NewAuditPage() {
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [mode, setMode] = useState<ClaimMode>('pre_submission');
  const [insurer, setInsurer] = useState('');
  const [files, setFiles] = useState<PickedFile[]>([]);
  const [consent, setConsent] = useState(false);
  const [givenBy, setGivenBy] = useState('patient');
  const [claimId, setClaimId] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const create = useCreateClaim();
  const recordConsent = useRecordConsent();
  const startRun = useStartRun();

  const valid = files.filter((f) => !rejectReason(f.file));
  const covered = coverage(mode, valid);
  const missing = requirements(mode).filter((r) => r.required && !covered.get(r.id));

  function patch(id: string, update: Partial<PickedFile>) {
    setFiles((list) => list.map((f) => (f.id === id ? { ...f, ...update } : f)));
  }

  async function run() {
    setBusy(true);
    setError(null);
    try {
      // Reuse the claim if a previous attempt created it and stopped part-way.
      const id =
        claimId ??
        (
          await create.mutateAsync({
            mode,
            ...(insurer.trim() ? { insurer_hint: insurer.trim() } : {}),
          })
        ).claim_id;
      setClaimId(id);
      for (const f of valid.filter((v) => v.state !== 'uploaded')) {
        patch(f.id, { state: 'uploading', progress: 0 });
        await uploadDocument(id, f.file, f.type, (progress) => {
          patch(f.id, { progress });
        });
        patch(f.id, { state: 'uploaded', progress: 1 });
      }
      await recordConsent.mutateAsync({ claimId: id, givenBy });
      const started = await startRun.mutateAsync(id);
      void navigate(`/claims/${id}?run=${started.run_id}`);
    } catch (e) {
      setError(e instanceof ApiProblem || e instanceof Error ? e : new Error('Upload failed'));
      setFiles((list) =>
        list.map((f) =>
          f.state === 'uploading'
            ? { ...f, state: 'error', error: 'Upload stopped. Run again to retry.' }
            : f,
        ),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <PageHeader
        title="New audit"
        eyebrow="Worklist / New audit"
        description="Arzi reads the documents, removes patient identifiers, applies IRDAI and policy rules, and shows every flag with its ₹ impact."
      />

      <ol className="grid grid-cols-3 gap-3" aria-label="Steps">
        {STEPS.map((label, i) => (
          <li
            key={label}
            aria-current={i === step ? 'step' : undefined}
            className={cn(
              'flex items-center gap-3 rounded-lg border px-4 py-3',
              i === step ? 'border-navy bg-surface shadow-card' : 'border-border bg-canvas',
            )}
          >
            <span
              className={cn(
                'grid size-6 place-content-center rounded-full text-xs font-semibold',
                i < step
                  ? 'bg-success text-white'
                  : i === step
                    ? 'bg-navy text-white'
                    : 'bg-sunken text-ink-muted',
              )}
            >
              {i + 1}
            </span>
            <span className={cn('text-sm font-medium', i === step ? 'text-ink' : 'text-ink-muted')}>
              {label}
            </span>
          </li>
        ))}
      </ol>

      <Card className="p-6">
        {step === 0 ? (
          <fieldset className="space-y-5">
            <legend className="text-base font-semibold">What stage is this claim at?</legend>
            <div className="grid gap-3 md:grid-cols-3">
              {(Object.keys(MODE) as ClaimMode[]).map((m) => {
                const Icon = MODE_ICON[m];
                const id = `mode-${m}`;
                return (
                  <label
                    key={m}
                    htmlFor={id}
                    className={cn(
                      'relative cursor-pointer rounded-xl border p-4 transition-colors has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-navy',
                      mode === m
                        ? 'border-navy bg-navy-soft/50 ring-1 ring-navy'
                        : 'border-border hover:border-border-strong',
                      claimId && 'cursor-not-allowed opacity-60',
                    )}
                  >
                    <input
                      id={id}
                      type="radio"
                      name="mode"
                      value={m}
                      checked={mode === m}
                      disabled={Boolean(claimId)}
                      onChange={() => {
                        setMode(m);
                      }}
                      className="sr-only"
                    />
                    <Icon className="size-5 text-accent" aria-hidden />
                    <p className="mt-3 font-semibold">{MODE[m].label}</p>
                    <p className="mt-1 text-[0.8125rem] text-ink-muted">{MODE_BLURB[m]}</p>
                    <p className="mt-3 text-xs text-ink-subtle">Needs: {MODE[m].needs}</p>
                  </label>
                );
              })}
            </div>
            <div className="max-w-sm space-y-1.5">
              <Label htmlFor="insurer">
                Insurer or TPA <span className="font-normal text-ink-subtle">(optional)</span>
              </Label>
              <Input
                id="insurer"
                value={insurer}
                onChange={(e) => {
                  setInsurer(e.target.value);
                }}
                placeholder="Read from the policy if left blank"
              />
            </div>
          </fieldset>
        ) : step === 1 ? (
          <FilePicker
            mode={mode}
            files={files}
            locked={busy}
            onAdd={(added) => {
              setFiles((list) => [
                ...list,
                ...added.map((file) => ({
                  id: crypto.randomUUID(),
                  file,
                  type: null,
                  progress: 0,
                  state: 'ready' as const,
                })),
              ]);
            }}
            onRemove={(id) => {
              setFiles((list) => list.filter((f) => f.id !== id));
            }}
            onType={(id, type: DocType | null) => {
              patch(id, { type });
            }}
          />
        ) : (
          <div className="space-y-6">
            <dl className="grid gap-4 sm:grid-cols-3">
              <div>
                <dt className="text-xs text-ink-subtle">Claim type</dt>
                <dd className="font-medium">{MODE[mode].label}</dd>
              </div>
              <div>
                <dt className="text-xs text-ink-subtle">Documents</dt>
                <dd className="font-medium">{valid.length} files</dd>
              </div>
              <div>
                <dt className="text-xs text-ink-subtle">Insurer</dt>
                <dd className="font-medium">{insurer.trim() || 'From the policy'}</dd>
              </div>
            </dl>
            {missing.length ? (
              <p className="rounded-md border border-warning-border bg-warning-bg px-3 py-2 text-[0.8125rem] text-warning">
                Not found by file name: {missing.map((m) => m.label.toLowerCase()).join(', ')}. You
                can still run the audit; Arzi reads each document and flags what is missing.
              </p>
            ) : null}
            <div className="rounded-xl border border-border bg-canvas p-4">
              <div className="flex items-start gap-3">
                <Checkbox
                  id="consent"
                  checked={consent}
                  onCheckedChange={(v) => {
                    setConsent(v === true);
                  }}
                  className="mt-0.5"
                />
                <div className="space-y-2">
                  <Label htmlFor="consent" className="leading-snug">
                    Consent was given for Arzi to process these documents to audit this claim.
                  </Label>
                  <p className="text-[0.8125rem] text-ink-muted">
                    Purpose: claim audit (DPDP). Identifiers are removed before any AI reasoning,
                    documents stay in Mumbai (asia-south1) and are deleted after 30 days. The
                    consent is recorded in the claim’s audit log.
                  </p>
                  <div className="flex items-center gap-2">
                    <Label htmlFor="given-by" className="text-xs font-normal text-ink-muted">
                      Given by
                    </Label>
                    <Select
                      id="given-by"
                      value={givenBy}
                      onChange={(e) => {
                        setGivenBy(e.target.value);
                      }}
                      className="w-56"
                    >
                      <option value="patient">Patient</option>
                      <option value="family member">Family member</option>
                      <option value="authorised representative">Authorised representative</option>
                    </Select>
                  </div>
                </div>
              </div>
            </div>
            {error ? <ProblemAlert error={error} /> : null}
          </div>
        )}
      </Card>

      <div className="flex items-center justify-between">
        <Button
          variant="ghost"
          onClick={() => {
            if (step === 0) void navigate('/worklist');
            else setStep(step - 1);
          }}
          disabled={busy}
        >
          <ArrowLeft aria-hidden />
          {step === 0 ? 'Cancel' : 'Back'}
        </Button>
        {step < 2 ? (
          <Button
            onClick={() => {
              setStep(step + 1);
            }}
            disabled={step === 1 && valid.length === 0}
          >
            Continue
            <ArrowRight aria-hidden />
          </Button>
        ) : (
          <Button
            onClick={() => void run()}
            disabled={!consent || valid.length === 0}
            loading={busy}
          >
            {busy ? null : <Play aria-hidden />}
            {busy ? 'Uploading and starting…' : 'Run audit'}
          </Button>
        )}
      </div>
    </div>
  );
}
