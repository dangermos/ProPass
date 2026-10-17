import { describe, expect, it } from 'vitest';
import { money, percent, rateColor, shortId } from '../ui';

describe('formatting', () => {
  it('formats money as US dollars with cents', () => {
    expect(money(0)).toBe('$0.00');
    expect(money(1234.5)).toBe('$1,234.50');
  });
  it('formats rates as percentages and shows a dash for missing values', () => {
    expect(percent(0.8)).toBe('80%');
    expect(percent(0.955, 1)).toBe('95.5%');
    expect(percent(null)).toBe('—');
    expect(percent(undefined)).toBe('—');
    expect(percent(0)).toBe('0%');
  });
  it('shortens IDs to eight upper-case characters', () => {
    expect(shortId('3f2a9c1e-77aa-4b1f')).toBe('3F2A9C1E');
  });
  it('colors pass rates on the same thresholds as the benchmark report', () => {
    expect(rateColor(1)).toBe('#2ea043');
    expect(rateColor(0.8)).toBe('#2ea043');
    expect(rateColor(0.6)).toBe('#d29922');
    expect(rateColor(0.5)).toBe('#d29922');
    expect(rateColor(0.4)).toBe('#f85149');
  });
});
