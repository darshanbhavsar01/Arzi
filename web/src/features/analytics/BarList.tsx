/** Horizontal bars as a labelled list: readable by screen readers, no chart library. */
import { formatMoneyCompact } from '@/lib/format';

import type { Bar } from './aggregate';

export function BarList({
  title,
  bars,
  tone = 'navy',
}: {
  title: string;
  bars: Bar[];
  tone?: 'navy' | 'accent' | 'success';
}) {
  const max = Math.max(1, ...bars.map((b) => b.value));
  const fill = { navy: 'fill-navy', accent: 'fill-accent', success: 'fill-success' }[tone];
  return (
    <section
      aria-label={title}
      className="rounded-xl border border-border bg-surface p-4 shadow-card"
    >
      <h2 className="text-sm font-semibold text-ink">{title}</h2>
      {bars.length === 0 ? (
        <p className="mt-3 text-sm text-ink-subtle">Nothing to show yet.</p>
      ) : (
        <ul className="mt-3 space-y-2.5">
          {bars.map((b) => (
            <li key={b.label}>
              <div className="flex justify-between gap-3 text-xs text-ink-muted">
                <span className="truncate">{b.label}</span>
                <span className="font-medium tabular-nums text-ink">
                  {formatMoneyCompact(b.value)}
                </span>
              </div>
              <svg
                className="mt-1 h-2 w-full"
                viewBox="0 0 100 2"
                preserveAspectRatio="none"
                aria-hidden
              >
                <rect width="100" height="2" rx="1" className="fill-slate" />
                <rect width={(b.value / max) * 100} height="2" rx="1" className={fill} />
              </svg>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
