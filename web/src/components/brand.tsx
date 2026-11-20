/** The Arzi mark (document + check) and wordmark, drawn as SVG so they stay crisp at any size. */
import { cn } from '@/lib/cn';

export function ArziMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 48 48" className={cn('size-8', className)} aria-hidden>
      <path
        d="M10 6.5A2.5 2.5 0 0 1 12.5 4H27l9 9v25.5a2.5 2.5 0 0 1-2.5 2.5h-21A2.5 2.5 0 0 1 10 38.5Z"
        className="fill-navy"
      />
      <path
        d="M13 8.5A1.5 1.5 0 0 1 14.5 7H25v8h8v21.5a1.5 1.5 0 0 1-1.5 1.5h-17A1.5 1.5 0 0 1 13 36.5Z"
        className="fill-white"
      />
      <rect x="16" y="18" width="11" height="2" rx="1" className="fill-slate" />
      <rect x="16" y="23" width="13" height="2" rx="1" className="fill-slate" />
      <rect x="16" y="28" width="8" height="2" rx="1" className="fill-slate" />
      <circle cx="34" cy="34" r="10" className="fill-cream" />
      <circle cx="34" cy="34" r="8.5" className="fill-accent" />
      <path
        d="m30 34.2 2.8 2.8 5.4-6"
        className="fill-none stroke-white"
        strokeWidth={2.4}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function ArziWordmark({ className }: { className?: string }) {
  return (
    <span
      role="img"
      aria-label="Arzi"
      className={cn(
        'relative inline-flex items-baseline text-lg font-semibold tracking-tight text-navy',
        className,
      )}
    >
      <span aria-hidden>arz</span>
      <span aria-hidden className="relative">
        ı
        <span className="absolute -top-0.5 left-1/2 size-1.5 -translate-x-1/2 rounded-full bg-accent" />
      </span>
    </span>
  );
}
