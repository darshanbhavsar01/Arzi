/** Sign-in: the brand story on cream, and the way into the workspace. */
import {
  ArrowRight,
  FileSearch,
  HeartHandshake,
  Lock,
  ScrollText,
  ShieldCheck,
} from 'lucide-react';
import { Link, useLocation, useNavigate } from 'react-router';

import { ArziMark, ArziWordmark } from '@/components/brand';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/primitives';
import { signIn } from '@/lib/session';

const PROOF = [
  {
    icon: FileSearch,
    title: 'Every likely deduction, before you file',
    body: 'The ₹ at risk on each bill line, with the exact policy clause or IRDAI rule and the fix.',
  },
  {
    icon: ScrollText,
    title: 'Appeals that cite, not guess',
    body: 'Amounts come only from a deterministic rules engine; every citation is checked against a whitelist.',
  },
  {
    icon: ShieldCheck,
    title: 'A person signs every appeal',
    body: 'Identifiers are redacted before any AI reasoning; signed letters are sealed with a SHA-256 hash.',
  },
] as const;

export default function SignInPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? '/worklist';

  function enter() {
    signIn();
    void navigate(from === '/sign-in' ? '/worklist' : from, { replace: true });
  }

  return (
    <div className="grid min-h-screen lg:grid-cols-[1.1fr_1fr]">
      <section className="relative hidden flex-col justify-between overflow-hidden bg-cream px-14 py-12 lg:flex">
        <div className="relative z-10 flex items-center gap-2.5">
          <ArziMark className="size-10" />
          <ArziWordmark className="text-2xl" />
        </div>
        <div className="relative z-10 max-w-lg">
          <h1 className="text-[2.25rem] leading-tight font-semibold tracking-tight text-navy">
            Your claim, defended before and after the insurer says no.
          </h1>
          <p className="mt-4 text-[0.9375rem] leading-relaxed text-ink-muted">
            Arzi audits hospital health-insurance claims against IRDAI rules and the policy wording,
            then drafts clause-cited appeals for a qualified person to review and sign.
          </p>
          <ul className="mt-10 space-y-6">
            {PROOF.map(({ icon: Icon, title, body }) => (
              <li key={title} className="flex gap-4">
                <span className="grid size-10 shrink-0 place-content-center rounded-lg bg-surface text-accent shadow-card">
                  <Icon className="size-5" aria-hidden />
                </span>
                <div>
                  <p className="font-semibold text-ink">{title}</p>
                  <p className="mt-0.5 text-ink-muted">{body}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>
        <p className="relative z-10 text-xs text-ink-subtle">
          Data at rest in Mumbai (asia-south1) · Google Cloud and Gemini · DPDP consent on every
          claim
        </p>
        <div
          className="pointer-events-none absolute -top-40 -right-40 size-[28rem] rounded-full border-[56px] border-cream-deep/70"
          aria-hidden
        />
      </section>

      <section className="flex flex-col items-center justify-center bg-surface px-6 py-12">
        <div className="w-full max-w-sm">
          <div className="mb-8 flex items-center gap-2 lg:hidden">
            <ArziMark className="size-9" />
            <ArziWordmark className="text-xl" />
          </div>
          <h2 className="text-xl font-semibold tracking-tight">Sign in to the claims desk</h2>
          <p className="mt-1.5 text-ink-muted">Sanjeevani Multispeciality Hospital, Ahmedabad</p>

          <div className="mt-8 rounded-xl border border-border bg-canvas p-5">
            <div className="flex items-center justify-between gap-2">
              <p className="font-semibold">Demo workspace</p>
              <Badge tone="warning">Synthetic data</Badge>
            </div>
            <p className="mt-1.5 text-[0.8125rem] text-ink-muted">
              Three fictional claims (a pre-submission audit, a deduction and a rejection) with
              synthetic documents. Nothing here is real patient data.
            </p>
            <Button size="lg" className="mt-4 w-full" onClick={enter}>
              Continue to the demo workspace
              <ArrowRight aria-hidden />
            </Button>
          </div>

          <div className="mt-6 flex items-start gap-3 text-[0.8125rem] text-ink-subtle">
            <Lock className="mt-0.5 size-4 shrink-0" aria-hidden />
            <p>
              Access is scoped to one hospital, and every action (uploads, corrections, drafts,
              signatures) is written to the claim’s audit log.
            </p>
          </div>

          <Link
            to="/check"
            className="mt-8 flex items-center gap-3 rounded-xl border border-cream-deep bg-cream px-4 py-3 hover:border-accent"
          >
            <HeartHandshake className="size-5 shrink-0 text-accent" aria-hidden />
            <span className="flex-1 text-sm">
              <span className="block font-semibold text-ink">A patient’s family?</span>
              <span className="text-ink-muted">
                Check a rejected or cut claim for free, in ગુજરાતી, हिन्दी or English.
              </span>
            </span>
            <ArrowRight className="size-4 text-ink-subtle" aria-hidden />
          </Link>
        </div>
      </section>
    </div>
  );
}
