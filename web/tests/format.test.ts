import { describe, expect, it } from 'vitest';

import {
  formatDate,
  formatDuration,
  formatMicroInr,
  formatMoney,
  formatMoneyCompact,
  formatRelative,
} from '@/lib/format';

describe('formatMoney (paise → en-IN)', () => {
  it.each([
    [15_761_250, '₹1,57,612.50'],
    [22_550_000, '₹2,25,500'],
    [90_000, '₹900'],
    [5, '₹0.05'],
    [0, '₹0'],
    [50_00_00_000, '₹50,00,000'],
    [1_23_45_67_890, '₹1,23,45,678.90'],
  ])('formats %i paise as %s', (paise, shown) => {
    expect(formatMoney(paise)).toBe(shown);
  });

  it('keeps paise for table alignment when asked', () => {
    expect(formatMoney(90_000, { exact: true })).toBe('₹900.00');
  });
});

describe('formatMoneyCompact', () => {
  it('is exact below a lakh, so KPIs match the rows', () => {
    expect(formatMoneyCompact(6_788_750)).toBe('₹67,887.50');
  });

  it('uses lakh and crore above that', () => {
    expect(formatMoneyCompact(15_761_250)).toBe('₹1.58 L');
    expect(formatMoneyCompact(31_000_000)).toBe('₹3.1 L');
    expect(formatMoneyCompact(2_40_00_00_000)).toBe('₹2.4 Cr');
  });
});

describe('dates and durations', () => {
  it('reads ISO calendar dates as local days', () => {
    expect(formatDate('2026-10-03')).toBe('3 Oct 2026');
    expect(formatDate(null)).toBe('—');
  });

  it('describes recent times relatively', () => {
    const now = new Date('2026-11-20T10:00:00Z').getTime();
    expect(formatRelative('2026-11-20T09:59:40Z', now)).toBe('just now');
    expect(formatRelative('2026-11-20T09:56:00Z', now)).toBe('4 min ago');
    expect(formatRelative('2026-11-20T07:00:00Z', now)).toBe('3 h ago');
  });

  it.each([
    [0.04, '< 0.1 s'],
    [2.34, '2.3 s'],
    [42, '42 s'],
    [75, '1 min 15 s'],
    [null, '—'],
  ])('formats %s seconds as %s', (seconds, shown) => {
    expect(formatDuration(seconds)).toBe(shown);
  });

  it('formats ledger micro-rupees', () => {
    expect(formatMicroInr(0)).toBe('₹0');
    expect(formatMicroInr(4_600_000)).toBe('₹4.60');
    expect(formatMicroInr(3_000)).toBe('< ₹0.01');
  });
});
