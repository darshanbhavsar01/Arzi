/** Arzi's domain primitives: money, statuses, severities, confidence, redaction, KPI tiles. */
import {
  AlertOctagon,
  CheckCircle2,
  CircleDashed,
  FileSignature,
  FileText,
  Loader2,
  Send,
  ShieldCheck,
  TriangleAlert,
  Upload,
} from 'lucide-react';
import type { ReactNode } from 'react';

import type { ClaimStatus, Severity } from '@/api/types';
import { Badge, badgeVariants } from '@/components/ui/primitives';
import { Tooltip } from '@/components/ui/overlays';
import { cn } from '@/lib/cn';
import { formatMoney, formatPercent } from '@/lib/format';
import { SEVERITY, STATUS } from '@/lib/labels';

// ------------------------------------------------------------------------- money

type MoneyTone = 'default' | 'risk' | 'recover' | 'muted';

/** An engine amount in paise, en-IN formatted with tabular figures. */
export function Money({
  paise,
  tone = 'default',
  exact = false,
  className,
}: {
  paise: number;
  tone?: MoneyTone;
  exact?: boolean;
  className?: string;
}) {
  return (
    <span
      className={cn(
        'tabular-nums whitespace-nowrap',
        tone === 'risk' && 'font-medium text-accent-strong',
        tone === 'recover' && 'font-medium text-success',
        tone === 'muted' && 'text-ink-subtle',
        className,
      )}
    >
      {formatMoney(paise, { exact })}
    </span>
  );
}

// ------------------------------------------------------------------------- status

const STATUS_ICON: Record<ClaimStatus, typeof FileText> = {
  draft: CircleDashed,
  documents_uploaded: Upload,
  processing: Loader2,
  audited: CheckCircle2,
  appeal_drafted: FileText,
  in_review: Send,
  signed: FileSignature,
  exported: FileSignature,
  failed: AlertOctagon,
};

export function StatusPill({ status }: { status: ClaimStatus }) {
  const { label, tone } = STATUS[status];
  const Icon = STATUS_ICON[status];
  return (
    <Badge tone={tone}>
      <Icon className={cn(status === 'processing' && 'animate-spin')} aria-hidden />
      {label}
    </Badge>
  );
}

// ------------------------------------------------------------------------- severity

const SEVERITY_DOT: Record<Severity, string> = {
  critical: 'bg-danger',
  high: 'bg-accent',
  medium: 'bg-warning',
  low: 'bg-info',
  info: 'bg-slate',
};

export function SeverityDot({ severity, className }: { severity: Severity; className?: string }) {
  return (
    <span
      className={cn('inline-block size-2 shrink-0 rounded-full', SEVERITY_DOT[severity], className)}
      aria-hidden
    />
  );
}

/** Severity as dot + word, so colour is never the only signal. */
export function SeverityLabel({ severity }: { severity: Severity }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-medium text-ink-muted">
      <SeverityDot severity={severity} />
      {SEVERITY[severity].label}
    </span>
  );
}

/** Worklist cell: one dot per flag (highest first) and the count. */
export function SeveritySummary({ severities }: { severities: Severity[] }) {
  if (severities.length === 0) return <span className="text-ink-subtle">—</span>;
  const sorted = [...severities].sort((a, b) => SEVERITY[b].rank - SEVERITY[a].rank);
  const high = sorted.filter((s) => SEVERITY[s].rank >= 3).length;
  return (
    <span
      className="inline-flex items-center gap-1.5"
      aria-label={`${String(severities.length)} flags, ${String(high)} high or critical`}
    >
      <span className="inline-flex -space-x-0.5" aria-hidden>
        {sorted.slice(0, 5).map((s, i) => (
          <SeverityDot key={`${s}-${String(i)}`} severity={s} className="ring-2 ring-surface" />
        ))}
      </span>
      <span className="tabular-nums text-ink-muted">{severities.length}</span>
    </span>
  );
}

// ------------------------------------------------------------------------- confidence

export function ConfidenceMark({ value }: { value: number }) {
  const low = value < 0.8;
  const bars = value >= 0.95 ? 3 : value >= 0.8 ? 2 : 1;
  return (
    <Tooltip
      content={
        low
          ? `Extraction confidence ${formatPercent(value)}: a person should confirm this line.`
          : `Extraction confidence ${formatPercent(value)}`
      }
    >
      <button
        type="button"
        className={cn(
          'inline-flex items-end gap-0.5 rounded px-1 py-0.5',
          low ? 'text-warning' : 'text-ink-subtle',
        )}
        aria-label={`Confidence ${formatPercent(value)}${low ? ', needs confirmation' : ''}`}
      >
        {[1, 2, 3].map((n) => (
          <span
            key={n}
            className={cn(
              'w-1 rounded-sm',
              n === 1 ? 'h-1.5' : n === 2 ? 'h-2.5' : 'h-3.5',
              n <= bars ? 'bg-current' : 'bg-border-strong',
            )}
          />
        ))}
      </button>
    </Tooltip>
  );
}

// ------------------------------------------------------------------------- redaction

const REDACTION_LABEL: Record<string, string> = {
  name: 'names',
  phone: 'phone numbers',
  email: 'emails',
  address: 'addresses',
  aadhaar: 'Aadhaar-like numbers',
  pan: 'PAN-like codes',
  uhid: 'UHIDs',
  ip_number: 'IP numbers',
  policy_number: 'policy numbers',
  member_id: 'member IDs',
  claim_number: 'claim numbers',
};

export function RedactionBadge({ counts }: { counts: Record<string, number> }) {
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  const detail = Object.entries(counts)
    .map(([kind, n]) => `${String(n)} ${REDACTION_LABEL[kind] ?? kind}`)
    .join(' · ');
  return (
    <Tooltip
      content={
        <>
          Removed before any AI reasoning, replaced with stable pseudonyms.
          {detail ? <span className="mt-1 block text-white/80">{detail}</span> : null}
        </>
      }
    >
      <button type="button" className={cn(badgeVariants({ tone: 'success' }), 'cursor-default')}>
        <ShieldCheck aria-hidden />
        {total} identifiers redacted
      </button>
    </Tooltip>
  );
}

// ------------------------------------------------------------------------- KPI tile

export function KpiTile({
  label,
  value,
  hint,
  tone = 'default',
  icon,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: 'default' | 'risk' | 'recover';
  icon?: ReactNode;
}) {
  return (
    <div className="rounded-xl border border-border bg-surface px-4 py-3.5 shadow-card">
      <div className="flex items-center justify-between gap-2 text-xs font-medium text-ink-muted">
        {label}
        {icon ? <span className="text-ink-subtle [&_svg]:size-4">{icon}</span> : null}
      </div>
      <div
        className={cn(
          'mt-1.5 text-[1.375rem] leading-tight font-semibold tabular-nums',
          tone === 'risk' && 'text-accent-strong',
          tone === 'recover' && 'text-success',
        )}
      >
        {value}
      </div>
      {hint ? <div className="mt-1 text-xs text-ink-subtle">{hint}</div> : null}
    </div>
  );
}

export function WarningNote({ children }: { children: ReactNode }) {
  return (
    <p className="flex items-start gap-2 rounded-md border border-warning-border bg-warning-bg px-3 py-2 text-[0.8125rem] text-warning">
      <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
      <span>{children}</span>
    </p>
  );
}
