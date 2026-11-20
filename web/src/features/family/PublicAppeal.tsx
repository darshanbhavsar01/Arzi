/**
 * Free check only: draft the appeal, let the family read it, sign it with their name, download.
 * The family is the person who reviews and signs, so the human-in-the-loop rule still holds.
 */
import { Download, FileSignature, Scale } from 'lucide-react';
import { useState } from 'react';

import {
  publicAppealPdf,
  useDraftPublicAppeal,
  usePublicAppeal,
  useSignPublicAppeal,
} from '@/api/family';
import type { FamilyView } from '@/api/types';
import { Money } from '@/components/domain';
import { ProblemAlert } from '@/components/states';
import { Button } from '@/components/ui/button';
import { Checkbox, Input, Label } from '@/components/ui/primitives';
import { ruleTitle } from '@/lib/labels';
import type { FamilyStrings } from '@/features/family/strings';

export function PublicAppeal({
  token,
  view,
  t,
}: {
  token: string;
  view: FamilyView;
  t: FamilyStrings;
}) {
  const existing = usePublicAppeal(token, view.appeal !== null);
  const draft = useDraftPublicAppeal(token);
  const sign = useSignPublicAppeal(token);
  const [name, setName] = useState('');
  const [agreed, setAgreed] = useState(false);
  // Newest first: the signed version, then what the server holds, then the fresh draft.
  const appeal = sign.data ?? existing.data ?? draft.data;

  if (!appeal) {
    if (!view.can_draft_appeal) return null;
    return (
      <section className="rounded-2xl border border-cream-deep bg-surface p-5 shadow-card">
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <Scale className="size-5 text-accent" aria-hidden />
          {t.draftTitle}
        </h2>
        <p className="mt-2 text-base leading-relaxed text-ink-muted">{t.draftBody}</p>
        {draft.isError ? <ProblemAlert error={draft.error} className="mt-3" /> : null}
        <Button
          size="lg"
          className="mt-4 h-12 w-full text-base"
          onClick={() => {
            draft.mutate();
          }}
          loading={draft.isPending}
        >
          {t.draftButton}
        </Button>
      </section>
    );
  }

  const c = appeal.content;
  const signed = appeal.signature;
  return (
    <section className="rounded-2xl border border-cream-deep bg-surface p-5 shadow-card" lang="en">
      <h2 className="flex items-center gap-2 text-lg font-semibold">
        <FileSignature className="size-5 text-accent" aria-hidden />
        {signed ? t.signedBy(signed.reviewer_name) : t.signTitle}
      </h2>
      <p className="mt-1 text-sm text-ink-subtle">{t.appealEnglishNote}</p>
      <div className="mt-4 space-y-3 rounded-xl bg-canvas p-4 text-[0.9375rem] leading-relaxed">
        <p className="font-semibold">{c.subject.text}</p>
        <p>{c.facts.text}</p>
        {c.items.map((item) => (
          <div key={item.flag_id} className="border-t border-border pt-3">
            <p className="flex items-baseline justify-between gap-3 font-medium">
              {ruleTitle(item.rule_id)} <Money paise={item.amount} tone="recover" />
            </p>
            <p className="mt-1 text-ink-muted">{item.argument.text}</p>
          </div>
        ))}
        <p className="border-t border-border pt-3 font-medium">{c.relief.text}</p>
      </div>
      {signed ? (
        <div className="mt-4 space-y-2">
          <Button asChild size="lg" className="h-12 w-full text-base">
            <a href={publicAppealPdf(token)} download>
              <Download aria-hidden />
              {t.download}
            </a>
          </Button>
          <p className="font-mono text-xs break-all text-ink-subtle">
            SHA-256 {signed.content_sha256}
          </p>
        </div>
      ) : (
        <form
          className="mt-4 space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            sign.mutate(name.trim());
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="signer" className="text-base">
              {t.signName}
            </Label>
            <Input
              id="signer"
              value={name}
              onChange={(e) => {
                setName(e.target.value);
              }}
              autoComplete="name"
              className="h-12 text-base"
              required
              minLength={2}
            />
          </div>
          <div className="flex items-start gap-3">
            <Checkbox
              id="signer-agree"
              checked={agreed}
              onCheckedChange={(v) => {
                setAgreed(v === true);
              }}
              className="mt-1 size-5"
            />
            <Label htmlFor="signer-agree" className="text-base font-normal leading-snug">
              {t.signDeclaration}
            </Label>
          </div>
          {sign.isError ? <ProblemAlert error={sign.error} /> : null}
          <Button
            type="submit"
            size="lg"
            className="h-12 w-full text-base"
            disabled={!agreed || name.trim().length < 2}
            loading={sign.isPending}
          >
            {t.signButton}
          </Button>
        </form>
      )}
    </section>
  );
}
