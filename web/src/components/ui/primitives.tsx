/** Small, stateless building blocks: badge, card, form fields, skeleton, progress, separator. */
import { cva, type VariantProps } from 'class-variance-authority';
import { Check, ChevronDown } from 'lucide-react';
import { Checkbox as CheckboxPrimitive, Label as LabelPrimitive } from 'radix-ui';
import type { ComponentProps, HTMLAttributes, SelectHTMLAttributes } from 'react';

import { cn } from '@/lib/cn';

export const badgeVariants = cva(
  'inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-medium [&_svg]:size-3',
  {
    variants: {
      tone: {
        neutral: 'border-border bg-sunken text-ink-muted',
        info: 'border-info-border bg-info-bg text-info',
        success: 'border-success-border bg-success-bg text-success',
        warning: 'border-warning-border bg-warning-bg text-warning',
        danger: 'border-danger-border bg-danger-bg text-danger',
        accent: 'border-accent-soft bg-accent-soft text-accent-strong',
        navy: 'border-navy bg-navy text-white',
      },
    },
    defaultVariants: { tone: 'neutral' },
  },
);

export type BadgeTone = NonNullable<VariantProps<typeof badgeVariants>['tone']>;

export function Badge({
  className,
  tone,
  ...props
}: HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn('rounded-xl border border-border bg-surface shadow-card', className)}
      {...props}
    />
  );
}

export function CardHeader({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        'flex items-start justify-between gap-3 border-b border-border px-5 py-3.5',
        className,
      )}
      {...props}
    />
  );
}

export function CardTitle({ className, children, ...props }: HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h2 className={cn('text-sm font-semibold text-ink', className)} {...props}>
      {children}
    </h2>
  );
}

const field =
  'w-full rounded-md border border-border-strong bg-surface px-3 text-sm text-ink shadow-card placeholder:text-ink-subtle focus-visible:border-navy focus-visible:outline-2 focus-visible:outline-offset-0 focus-visible:outline-navy/40 disabled:bg-sunken disabled:text-ink-subtle aria-invalid:border-danger';

export function Input({ className, ...props }: ComponentProps<'input'>) {
  return <input className={cn(field, 'h-9', className)} {...props} />;
}

export function Textarea({ className, ...props }: ComponentProps<'textarea'>) {
  return <textarea className={cn(field, 'min-h-24 py-2 leading-relaxed', className)} {...props} />;
}

/** Native select: fast, accessible and keyboard-friendly in dense tables and filter bars. */
export function Select({ className, children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <span className={cn('relative inline-flex w-full', className)}>
      <select className={cn(field, 'h-9 appearance-none pr-8')} {...props}>
        {children}
      </select>
      <ChevronDown
        className="pointer-events-none absolute top-1/2 right-2.5 size-4 -translate-y-1/2 text-ink-subtle"
        aria-hidden
      />
    </span>
  );
}

export function Label({ className, ...props }: ComponentProps<typeof LabelPrimitive.Root>) {
  return (
    <LabelPrimitive.Root
      className={cn('text-[0.8125rem] font-medium text-ink', className)}
      {...props}
    />
  );
}

export function Checkbox({ className, ...props }: ComponentProps<typeof CheckboxPrimitive.Root>) {
  return (
    <CheckboxPrimitive.Root
      className={cn(
        'peer grid size-4 shrink-0 place-content-center rounded-sm border border-border-strong bg-surface shadow-card focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-navy data-[state=checked]:border-navy data-[state=checked]:bg-navy data-[state=checked]:text-white',
        className,
      )}
      {...props}
    >
      <CheckboxPrimitive.Indicator>
        <Check className="size-3" strokeWidth={3} aria-hidden />
      </CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  );
}

export function Skeleton({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      aria-hidden
      className={cn('animate-pulse-soft rounded-md bg-sunken', className)}
      {...props}
    />
  );
}

export function Progress({
  value,
  label,
  className,
}: {
  value: number;
  label: string;
  className?: string;
}) {
  const pct = Math.round(Math.min(1, Math.max(0, value)) * 100);
  return (
    <progress className={cn('arzi-progress', className)} aria-label={label} value={pct} max={100} />
  );
}

export function Separator({ className }: { className?: string }) {
  return <hr className={cn('border-0 border-t border-border', className)} />;
}

export function Kbd({ className, ...props }: HTMLAttributes<HTMLElement>) {
  return (
    <kbd
      className={cn(
        'inline-flex h-5 min-w-5 items-center justify-center rounded border border-border-strong bg-surface px-1 font-mono text-[0.6875rem] text-ink-muted',
        className,
      )}
      {...props}
    />
  );
}
