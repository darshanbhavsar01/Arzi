/**
 * Presentation formatting. Money arrives as integer paise from the rules engine and is only ever
 * formatted here (en-IN grouping: ₹1,57,612.50); the UI never does arithmetic on amounts beyond
 * summing engine values for display.
 */

const rupees = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  minimumFractionDigits: 0,
  maximumFractionDigits: 2,
});
const rupeesExact = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/** `₹1,57,612.50`; whole rupees drop `.00` unless `exact` (tables align better with it). */
export function formatMoney(paise: number, { exact = false } = {}): string {
  const value = paise / 100;
  if (exact) return rupeesExact.format(value);
  return Number.isInteger(value) ? rupees.format(value) : rupeesExact.format(value);
}

/** KPI-sized amounts in Indian units: exact below a lakh (₹67,887.50), then ₹1.58 L · ₹2.4 Cr. */
export function formatMoneyCompact(paise: number): string {
  const value = paise / 100;
  const abs = Math.abs(value);
  if (abs >= 1e7) return `₹${trim(value / 1e7)} Cr`;
  if (abs >= 1e5) return `₹${trim(value / 1e5)} L`;
  return formatMoney(paise);
}

function trim(value: number): string {
  return value.toFixed(2).replace(/\.?0+$/, '');
}

const day = new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
const dayShort = new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short' });
const dateTime = new Intl.DateTimeFormat('en-IN', {
  day: 'numeric',
  month: 'short',
  hour: 'numeric',
  minute: '2-digit',
});

/** ISO date (YYYY-MM-DD) or timestamp → "12 Oct 2026". Dates are parsed as local calendar days. */
export function formatDate(value: string | null | undefined, { short = false } = {}): string {
  if (!value) return '—';
  const date = /^\d{4}-\d{2}-\d{2}$/.test(value) ? new Date(`${value}T00:00:00`) : new Date(value);
  return (short ? dayShort : day).format(date);
}

export function formatDateTime(value: string | null | undefined): string {
  return value ? dateTime.format(new Date(value)) : '—';
}

/** "just now", "4 min ago", "3 h ago", then the date. */
export function formatRelative(value: string | null | undefined, now = Date.now()): string {
  if (!value) return '—';
  const seconds = Math.round((now - new Date(value).getTime()) / 1000);
  if (seconds < 45) return 'just now';
  if (seconds < 3600) return `${String(Math.round(seconds / 60))} min ago`;
  if (seconds < 86_400) return `${String(Math.round(seconds / 3600))} h ago`;
  return formatDate(value);
}

/** 0.4 → "0.4 s", 75 → "1 min 15 s". */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return '—';
  if (seconds < 0.1) return '< 0.1 s';
  if (seconds < 10) return `${seconds.toFixed(1)} s`;
  if (seconds < 60) return `${String(Math.round(seconds))} s`;
  const minutes = Math.floor(seconds / 60);
  return `${String(minutes)} min ${String(Math.round(seconds % 60))} s`;
}

export function formatCount(n: number, one: string, many = `${one}s`): string {
  return `${n.toLocaleString('en-IN')} ${n === 1 ? one : many}`;
}

export function formatPercent(fraction: number): string {
  return `${String(Math.round(fraction * 100))}%`;
}

/** Integer micro-rupees (the cost ledger's unit) → "₹0.42". */
export function formatMicroInr(micro: number): string {
  const value = micro / 1e6;
  if (value === 0) return '₹0';
  return value < 0.01 ? '< ₹0.01' : `₹${value.toFixed(2)}`;
}
