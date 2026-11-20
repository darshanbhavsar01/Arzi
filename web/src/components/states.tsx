/** Page furniture and the non-happy states every data view needs: empty, error, loading. */
import { AlertTriangle, RotateCw } from 'lucide-react';
import type { ReactNode } from 'react';

import { ApiProblem } from '@/api/client';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/primitives';
import { cn } from '@/lib/cn';

export function PageHeader({
  title,
  description,
  eyebrow,
  actions,
  className,
}: {
  title: ReactNode;
  description?: ReactNode;
  eyebrow?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <header className={cn('flex flex-wrap items-end justify-between gap-4', className)}>
      <div className="min-w-0">
        {eyebrow ? <div className="mb-1 text-xs font-medium text-ink-subtle">{eyebrow}</div> : null}
        <h1 className="text-xl font-semibold tracking-tight text-ink">{title}</h1>
        {description ? <p className="mt-1 max-w-3xl text-ink-muted">{description}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </header>
  );
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: {
  icon: ReactNode;
  title: string;
  description: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        'flex flex-col items-center rounded-xl border border-dashed border-border-strong bg-cream/60 px-6 py-12 text-center',
        className,
      )}
    >
      <div className="mb-4 grid size-12 place-content-center rounded-full bg-surface text-accent shadow-card [&_svg]:size-6">
        {icon}
      </div>
      <h2 className="text-base font-semibold text-ink">{title}</h2>
      <p className="mt-1 max-w-md text-ink-muted">{description}</p>
      {action ? <div className="mt-5 flex flex-wrap justify-center gap-2">{action}</div> : null}
    </div>
  );
}

/** A failed request: what happened, what to do, and the request ID support can trace. */
export function ProblemAlert({
  error,
  onRetry,
  className,
}: {
  error: unknown;
  onRetry?: () => void;
  className?: string;
}) {
  const problem = error instanceof ApiProblem ? error : null;
  return (
    <div
      role="alert"
      className={cn(
        'flex items-start gap-3 rounded-lg border border-danger-border bg-danger-bg px-4 py-3 text-danger',
        className,
      )}
    >
      <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="font-medium">{problem?.title ?? 'Something went wrong'}</p>
        <p className="mt-0.5 text-[0.8125rem]">
          {problem?.detail ?? 'The request could not be completed. Try again in a moment.'}
        </p>
        {problem?.requestId ? (
          <p className="mt-1 font-mono text-xs opacity-80">Request ID {problem.requestId}</p>
        ) : null}
      </div>
      {onRetry ? (
        <Button variant="danger" size="sm" onClick={onRetry}>
          <RotateCw aria-hidden />
          Retry
        </Button>
      ) : null}
    </div>
  );
}

export function TableSkeleton({ rows = 6, columns = 6 }: { rows?: number; columns?: number }) {
  return (
    <div className="space-y-2 p-4" aria-label="Loading" role="status">
      {Array.from({ length: rows }, (_, r) => (
        <div key={r} className="flex gap-4">
          {Array.from({ length: columns }, (_, c) => (
            <Skeleton key={c} className={cn('h-5', c === 0 ? 'w-28' : 'flex-1')} />
          ))}
        </div>
      ))}
    </div>
  );
}
