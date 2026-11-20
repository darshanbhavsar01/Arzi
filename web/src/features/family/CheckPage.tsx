/**
 * The free "Check my rejection" (/check): a family uploads the letter, the policy and the bill,
 * consents, and is taken to a private page that shows the check running, then explains it.
 */
import '@fontsource/noto-sans-gujarati/400.css';
import '@fontsource/noto-sans-gujarati/600.css';
import '@fontsource/ibm-plex-sans-devanagari/400.css';
import '@fontsource/ibm-plex-sans-devanagari/600.css';

import { FileUp } from 'lucide-react';
import { useState } from 'react';
import { useNavigate } from 'react-router';

import { startCheck } from '@/api/family';
import type { Language } from '@/api/types';
import { ArziMark, ArziWordmark } from '@/components/brand';
import { ProblemAlert } from '@/components/states';
import { Button } from '@/components/ui/button';
import { Badge, Checkbox, Label } from '@/components/ui/primitives';
import { cn } from '@/lib/cn';
import {
  CHECK_STRINGS,
  initialLanguage,
  LANGUAGE_NAMES,
  rememberLanguage,
} from '@/features/family/strings';

type Field = 'letter' | 'policy' | 'bill' | 'discharge';
const FIELDS: { field: Field; multiple?: boolean; optional?: boolean }[] = [
  { field: 'letter' },
  { field: 'policy', multiple: true },
  { field: 'bill' },
  { field: 'discharge', optional: true },
];

export default function CheckPage() {
  const navigate = useNavigate();
  const [lang, setLang] = useState<Language>(initialLanguage);
  const [mode, setMode] = useState<'post_rejection' | 'post_deduction'>('post_rejection');
  const [files, setFiles] = useState<Partial<Record<Field, File[]>>>({});
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const t = CHECK_STRINGS[lang];
  const ready =
    consent && Boolean(files.letter?.length && files.policy?.length && files.bill?.length);

  async function submit() {
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.append('mode', mode);
    form.append('consent', 'true');
    form.append('given_by', 'policyholder or family');
    for (const { field } of FIELDS)
      for (const file of files[field] ?? []) form.append(field, file, file.name);
    try {
      const started = await startCheck(form);
      void navigate(started.url_path);
    } catch (e) {
      setError(e);
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-cream" lang={lang}>
      <header className="mx-auto flex max-w-xl items-center gap-2 px-4 py-4">
        <ArziMark className="size-8" />
        <ArziWordmark />
        <Badge tone="success" className="ml-1">
          {t.free}
        </Badge>
        <div
          role="group"
          aria-label="Language"
          className="ml-auto flex rounded-full bg-surface p-1 shadow-card"
        >
          {(['gu', 'hi', 'en'] as const).map((l) => (
            <button
              key={l}
              type="button"
              lang={l}
              aria-pressed={lang === l}
              onClick={() => {
                setLang(l);
                rememberLanguage(l);
              }}
              className={cn(
                'min-h-10 rounded-full px-3 text-sm font-medium',
                lang === l ? 'bg-navy text-white' : 'text-ink-muted',
              )}
            >
              {LANGUAGE_NAMES[l]}
            </button>
          ))}
        </div>
      </header>
      <main className="mx-auto max-w-xl px-4 pb-10">
        <h1 className="text-[1.625rem] leading-snug font-semibold tracking-tight">{t.title}</h1>
        <p className="mt-3 text-base leading-relaxed text-ink-muted">{t.intro}</p>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
          className="mt-6 space-y-5 rounded-2xl bg-surface p-5 shadow-card"
        >
          <fieldset>
            <legend className="text-base font-semibold">{t.decision}</legend>
            <div className="mt-3 grid grid-cols-2 gap-2">
              {(['post_rejection', 'post_deduction'] as const).map((m) => (
                <label
                  key={m}
                  className={cn(
                    'flex min-h-12 cursor-pointer items-center justify-center rounded-xl border px-3 text-center text-base font-medium has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-navy',
                    mode === m ? 'border-navy bg-navy text-white' : 'border-border-strong',
                  )}
                >
                  <input
                    type="radio"
                    name="mode"
                    value={m}
                    checked={mode === m}
                    onChange={() => {
                      setMode(m);
                    }}
                    className="sr-only"
                  />
                  {m === 'post_rejection' ? t.rejected : t.partlyPaid}
                </label>
              ))}
            </div>
          </fieldset>

          {FIELDS.map(({ field, multiple, optional }) => {
            const picked = files[field] ?? [];
            const id = `check-${field}`;
            return (
              <div key={field}>
                <Label htmlFor={id} className="text-base">
                  {t[field]}{' '}
                  {optional ? (
                    <span className="font-normal text-ink-subtle">({t.optional})</span>
                  ) : null}
                </Label>
                <label
                  htmlFor={id}
                  className="mt-1.5 flex min-h-12 cursor-pointer items-center gap-3 rounded-xl border border-dashed border-border-strong bg-canvas px-4 py-3 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-navy"
                >
                  <FileUp className="size-5 shrink-0 text-accent" aria-hidden />
                  <span
                    className={cn(
                      'min-w-0 flex-1 truncate',
                      picked.length ? 'text-ink' : 'text-ink-subtle',
                    )}
                  >
                    {picked.length ? picked.map((f) => f.name).join(', ') : t.choose}
                  </span>
                  <input
                    id={id}
                    type="file"
                    multiple={multiple}
                    accept=".pdf,.jpg,.jpeg,.png"
                    className="sr-only"
                    onChange={(e) => {
                      setFiles({ ...files, [field]: Array.from(e.target.files ?? []) });
                    }}
                  />
                </label>
              </div>
            );
          })}

          <div className="flex items-start gap-3 rounded-xl bg-canvas p-3">
            <Checkbox
              id="check-consent"
              checked={consent}
              onCheckedChange={(v) => {
                setConsent(v === true);
              }}
              className="mt-1 size-5"
            />
            <Label
              htmlFor="check-consent"
              className="text-[0.9375rem] font-normal leading-snug text-ink-muted"
            >
              {t.consent}
            </Label>
          </div>
          {error ? <ProblemAlert error={error} /> : null}
          <Button
            type="submit"
            size="lg"
            className="h-12 w-full text-base"
            disabled={!ready}
            loading={busy}
          >
            {t.submit}
          </Button>
          <p className="text-center text-sm text-ink-subtle">{t.privacy}</p>
        </form>
      </main>
    </div>
  );
}
