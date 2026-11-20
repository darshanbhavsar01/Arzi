/**
 * Where the appeal goes. GRO and Bima Bharosa are always open; the Ombudsman is disabled, with
 * the reason and its checklist, until the insurer has had its chance. Details of an earlier
 * written complaint (if any) feed the Ombudsman checks.
 */
import { CheckCircle2, Circle, CircleSlash, Clock4 } from 'lucide-react';
import { useState } from 'react';

import { useForums } from '@/api/queries';
import type { AppealForum, GroComplaint } from '@/api/types';
import { CitationChip } from '@/components/CitationChip';
import { ProblemAlert } from '@/components/states';
import { Button } from '@/components/ui/button';
import { Input, Label, Select, Skeleton } from '@/components/ui/primitives';
import { cn } from '@/lib/cn';
import { FORUM } from '@/lib/labels';

export function ForumPicker({
  claimId,
  onDraft,
  drafting,
}: {
  claimId: string;
  onDraft: (forum: AppealForum, complaint: GroComplaint | null) => void;
  drafting: boolean;
}) {
  const [forum, setForum] = useState<AppealForum>('insurer_gro');
  const [filedOn, setFiledOn] = useState('');
  const [outcome, setOutcome] = useState<GroComplaint['outcome'] | ''>('');
  const [repliedOn, setRepliedOn] = useState('');
  const complaint: GroComplaint | null =
    filedOn && outcome ? { filed_on: filedOn, outcome, replied_on: repliedOn || null } : null;
  const forums = useForums(claimId, complaint);
  const chosen = forums.data?.find((f) => f.forum === forum);

  return (
    <div className="space-y-5">
      {forums.isError ? (
        <ProblemAlert error={forums.error} onRetry={() => void forums.refetch()} />
      ) : null}
      <fieldset>
        <legend className="mb-3 text-base font-semibold">Where should this appeal go?</legend>
        <div className="grid gap-3 lg:grid-cols-3">
          {forums.isPending
            ? [0, 1, 2].map((i) => <Skeleton key={i} className="h-44" />)
            : (forums.data ?? []).map((option) => {
                const id = `forum-${option.forum}`;
                const disabled = !option.eligible;
                return (
                  <label
                    key={option.forum}
                    htmlFor={id}
                    className={cn(
                      'flex flex-col rounded-xl border p-4 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-navy',
                      forum === option.forum
                        ? 'border-navy bg-navy-soft/50 ring-1 ring-navy'
                        : 'border-border',
                      disabled
                        ? 'cursor-not-allowed bg-sunken'
                        : 'cursor-pointer hover:border-border-strong',
                    )}
                  >
                    <input
                      id={id}
                      type="radio"
                      name="forum"
                      className="sr-only"
                      checked={forum === option.forum}
                      disabled={disabled}
                      onChange={() => {
                        setForum(option.forum);
                      }}
                    />
                    <span className="flex items-center justify-between gap-2">
                      <span className="font-semibold">{FORUM[option.forum].label}</span>
                      {disabled ? (
                        <CircleSlash
                          className="size-4 text-ink-subtle"
                          aria-label="Not available yet"
                        />
                      ) : (
                        <CheckCircle2 className="size-4 text-success" aria-label="Available" />
                      )}
                    </span>
                    <span className="mt-1 text-[0.8125rem] text-ink-muted">
                      {FORUM[option.forum].blurb}
                    </span>
                    {option.response_window ? (
                      <span className="mt-2 inline-flex items-center gap-1 text-xs text-ink-subtle">
                        <Clock4 className="size-3.5" aria-hidden />
                        Reply expected in {option.response_window}
                      </span>
                    ) : null}
                    {option.reason ? (
                      <span className="mt-2 text-xs font-medium text-warning">{option.reason}</span>
                    ) : null}
                    {option.checks.length ? (
                      <ul className="mt-3 space-y-1.5 border-t border-border pt-3">
                        {option.checks.map((check) => (
                          <li
                            key={check.code}
                            className="flex items-start gap-1.5 text-xs text-ink-muted"
                          >
                            {check.met ? (
                              <CheckCircle2
                                className="mt-px size-3.5 shrink-0 text-success"
                                aria-hidden
                              />
                            ) : (
                              <Circle
                                className="mt-px size-3.5 shrink-0 text-border-strong"
                                aria-hidden
                              />
                            )}
                            <span>
                              {check.label}
                              <span className="sr-only">
                                {check.met
                                  ? ': met'
                                  : check.met === false
                                    ? ': not met'
                                    : ': not known yet'}
                              </span>
                            </span>
                          </li>
                        ))}
                      </ul>
                    ) : null}
                    <span className="mt-auto flex flex-wrap gap-1 pt-3">
                      {option.citations.map((c) => (
                        <CitationChip key={c} refId={c} />
                      ))}
                    </span>
                  </label>
                );
              })}
        </div>
      </fieldset>

      <fieldset className="rounded-xl border border-border bg-canvas p-4">
        <legend className="px-1 text-sm font-semibold">
          Earlier written complaint to the insurer{' '}
          <span className="font-normal text-ink-subtle">(needed for the Ombudsman)</span>
        </legend>
        <div className="mt-2 grid gap-3 sm:grid-cols-3">
          <div className="space-y-1.5">
            <Label htmlFor="gro-filed">Filed on</Label>
            <Input
              id="gro-filed"
              type="date"
              value={filedOn}
              onChange={(e) => {
                setFiledOn(e.target.value);
              }}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="gro-outcome">Outcome</Label>
            <Select
              id="gro-outcome"
              value={outcome}
              onChange={(e) => {
                setOutcome(e.target.value as GroComplaint['outcome'] | '');
              }}
            >
              <option value="">No complaint yet</option>
              <option value="rejected">Rejected</option>
              <option value="unsatisfactory">Unsatisfactory reply</option>
              <option value="no_reply">No reply</option>
              <option value="pending">Still waiting</option>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="gro-replied">Reply received on</Label>
            <Input
              id="gro-replied"
              type="date"
              value={repliedOn}
              onChange={(e) => {
                setRepliedOn(e.target.value);
              }}
              disabled={!outcome || outcome === 'no_reply' || outcome === 'pending'}
            />
          </div>
        </div>
      </fieldset>

      <div className="flex items-center justify-end gap-3">
        <p className="text-xs text-ink-subtle">
          The AppealDrafter writes a first draft; a qualified person reviews and signs it.
        </p>
        <Button
          size="lg"
          onClick={() => {
            onDraft(forum, complaint);
          }}
          disabled={!chosen?.eligible}
          loading={drafting}
        >
          {drafting ? 'Drafting the appeal…' : `Draft appeal for ${FORUM[forum].short}`}
        </Button>
      </div>
    </div>
  );
}
