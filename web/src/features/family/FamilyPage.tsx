/**
 * The family's page (/f/:token): what happened, why and what to do next, in Gujarati, Hindi or
 * English, by voice too. Mobile-first, no account, no names or ID numbers. A free check shows
 * its audit running first, then the explanation, then the appeal the family can sign.
 */
import '@fontsource/noto-sans-gujarati/400.css';
import '@fontsource/noto-sans-gujarati/600.css';
import '@fontsource/ibm-plex-sans-devanagari/400.css';
import '@fontsource/ibm-plex-sans-devanagari/600.css';

import { CheckCircle2, Clock4, Loader2, MapPin, ShieldCheck } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router';

import { ApiProblem } from '@/api/client';
import { useFamily, usePrepareFamily } from '@/api/family';
import type { FamilyExplanation, FamilyView, Language } from '@/api/types';
import { useRunEvents } from '@/api/useRunEvents';
import { ArziMark } from '@/components/brand';
import { stageViews } from '@/components/PipelineProgress';
import { Progress, Skeleton } from '@/components/ui/primitives';
import { cn } from '@/lib/cn';
import { formatMoney } from '@/lib/format';
import { AudioPlayer } from '@/features/family/AudioPlayer';
import { PublicAppeal } from '@/features/family/PublicAppeal';
import {
  formatDateIn,
  initialLanguage,
  LANGUAGE_NAMES,
  rememberLanguage,
  STRINGS,
  type FamilyStrings,
} from '@/features/family/strings';

const LANGS: Language[] = ['gu', 'hi', 'en'];

function Section({ title, items }: { title: string; items: FamilyExplanation['why'] }) {
  if (!items.length) return null;
  return (
    <section>
      <h2 className="text-lg font-semibold">{title}</h2>
      <ul className="mt-2 space-y-2">
        {items.map((p, i) => (
          <li key={i} className="text-[1.0625rem] leading-relaxed">
            {p.text}
          </li>
        ))}
      </ul>
    </section>
  );
}

function CheckRunning({
  token,
  t,
  onDone,
}: {
  token: string;
  t: FamilyStrings;
  onDone: () => void;
}) {
  const stream = useRunEvents('', 'public', `/api/v1/family/${token}/events`);
  const done = stageViews(stream.events, false).filter((s) => s.state === 'done').length;
  const notified = useRef(false);
  useEffect(() => {
    if (stream.state === 'completed' && !notified.current) {
      notified.current = true;
      onDone();
    }
  }, [stream.state, onDone]);
  return (
    <div className="rounded-2xl bg-surface p-6 text-center shadow-card" role="status">
      <Loader2 className="mx-auto size-8 animate-spin text-accent" aria-hidden />
      <h1 className="mt-4 text-xl font-semibold">{t.checking}</h1>
      <p className="mt-2 text-base text-ink-muted">{t.checkingBody}</p>
      <Progress value={done / 6} label={t.checking} className="mt-5" />
    </div>
  );
}

function Explanation({
  view,
  explanation,
  t,
  token,
}: {
  view: FamilyView;
  explanation: FamilyExplanation;
  t: FamilyStrings;
  token: string;
}) {
  const audio = view.audio.find((a) => a.lang === explanation.lang);
  return (
    <article lang={explanation.lang} className="space-y-6">
      <h1 className="text-[1.625rem] leading-snug font-semibold tracking-tight">
        {explanation.headline.text}
      </h1>
      {audio ? (
        <AudioPlayer key={audio.url} src={audio.url} seconds={audio.seconds} t={t} />
      ) : (
        <p className="text-sm text-ink-subtle">{t.noAudio}</p>
      )}
      {view.figures.length ? (
        <dl className="grid grid-cols-2 gap-3">
          {view.figures.map((f) => (
            <div
              key={f.key}
              className={cn(
                'rounded-2xl bg-surface p-4 shadow-card',
                f.key === 'recoverable' && 'ring-2 ring-success-border',
              )}
            >
              <dt className="text-sm text-ink-muted">{t.figures[f.key]}</dt>
              <dd
                className={cn(
                  'mt-1 text-[1.375rem] font-semibold tabular-nums',
                  f.key === 'at_risk' && 'text-accent-strong',
                  f.key === 'recoverable' && 'text-success',
                )}
              >
                {formatMoney(f.amount)}
              </dd>
            </div>
          ))}
        </dl>
      ) : null}
      <Section title={t.whatHappened} items={explanation.what_happened} />
      <Section title={t.why} items={explanation.why} />
      {explanation.next_steps.length ? (
        <section>
          <h2 className="text-lg font-semibold">{t.nextSteps}</h2>
          <ol className="mt-3 space-y-2">
            {explanation.next_steps.map((step, i) => (
              <li key={i} className="flex gap-3 rounded-xl bg-surface p-3.5 shadow-card">
                <span className="grid size-7 shrink-0 place-content-center rounded-full bg-navy text-sm font-semibold text-white">
                  {i + 1}
                </span>
                <span className="text-[1.0625rem] leading-relaxed">{step.text}</span>
              </li>
            ))}
          </ol>
        </section>
      ) : null}
      {view.appeal && view.purpose === 'family' ? (
        <section className="flex items-start gap-3 rounded-2xl bg-surface p-4 shadow-card">
          <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-success" aria-hidden />
          <div>
            <h2 className="font-semibold">{t.appealTitle}</h2>
            <p className="mt-0.5 text-ink-muted">{t.appealStatus[view.appeal.status]}</p>
          </div>
        </section>
      ) : null}
      {view.purpose === 'public_check' ? <PublicAppeal token={token} view={view} t={t} /> : null}
      <p className="flex items-start gap-3 rounded-2xl bg-cream-deep/60 p-4 text-[1.0625rem] leading-relaxed">
        <ShieldCheck className="mt-1 size-5 shrink-0 text-success" aria-hidden />
        {explanation.reassurance.text}
      </p>
    </article>
  );
}

export default function FamilyPage() {
  const { token = '' } = useParams();
  const family = useFamily(token);
  const prepare = usePrepareFamily(token);
  const [lang, setLang] = useState<Language>(initialLanguage);
  const t = STRINGS[lang];
  const view = family.data;
  const prepareOnce = useRef(false);

  const runPrepare = () => {
    if (prepareOnce.current) return;
    prepareOnce.current = true;
    prepare.mutate();
  };
  // A finished free check that has no explanation yet: write it now.
  useEffect(() => {
    if (
      view?.purpose === 'public_check' &&
      view.status === 'audited' &&
      view.explanations.length === 0
    )
      runPrepare();
  });

  const explanation = view?.explanations.find((e) => e.lang === lang) ?? view?.explanations[0];
  const running =
    view?.purpose === 'public_check' &&
    view.explanations.length === 0 &&
    ['processing', 'documents_uploaded'].includes(view.status);

  return (
    <div className="min-h-screen bg-cream">
      <header className="sticky top-0 z-10 border-b border-cream-deep bg-cream/95 backdrop-blur">
        <div className="mx-auto flex max-w-xl items-center gap-3 px-4 py-3">
          <ArziMark className="size-8" />
          <p className="min-w-0 flex-1 truncate text-sm font-semibold" lang="en">
            {view?.hospital_name ?? 'Arzi'}
          </p>
          <div
            role="group"
            aria-label={t.language}
            className="flex rounded-full bg-surface p-1 shadow-card"
          >
            {LANGS.map((l) => (
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
        </div>
      </header>

      <main className="mx-auto max-w-xl space-y-6 px-4 py-6" lang={lang}>
        {family.isPending ? (
          <div className="space-y-4" role="status" aria-label="Loading">
            <Skeleton className="h-9 w-4/5" />
            <Skeleton className="h-24" />
            <Skeleton className="h-40" />
          </div>
        ) : family.isError ? (
          <div className="rounded-2xl bg-surface p-6 text-center shadow-card" role="alert">
            <Clock4 className="mx-auto size-8 text-accent" aria-hidden />
            <h1 className="mt-3 text-xl font-semibold">
              {family.error instanceof ApiProblem && family.error.status === 404
                ? t.invalidTitle
                : 'Something went wrong'}
            </h1>
            <p className="mt-2 text-base text-ink-muted">{t.invalidBody}</p>
          </div>
        ) : running ? (
          <CheckRunning
            token={token}
            t={t}
            onDone={() => {
              void family.refetch().then(runPrepare);
            }}
          />
        ) : !explanation || !view ? (
          <div className="rounded-2xl bg-surface p-6 text-center shadow-card" role="status">
            <Loader2 className="mx-auto size-8 animate-spin text-accent" aria-hidden />
            <p className="mt-3 text-base">{t.writing}</p>
          </div>
        ) : (
          <Explanation view={view} explanation={explanation} t={t} token={token} />
        )}

        {view ? (
          <footer className="space-y-3 border-t border-cream-deep pt-5 text-sm text-ink-muted">
            {view.desk_contact ? (
              <p className="flex items-start gap-2">
                <MapPin className="mt-0.5 size-4 shrink-0" aria-hidden />
                <span>
                  <strong className="text-ink">{t.desk}</strong>
                  <br />
                  <span lang="en">{view.desk_contact}</span>
                </span>
              </p>
            ) : null}
            <p>{t.privacy(formatDateIn(lang, view.expires_at))}</p>
            <p>{t.disclaimer}</p>
          </footer>
        ) : null}
      </main>
    </div>
  );
}
