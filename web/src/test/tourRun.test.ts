import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { cartAt, endingOf, outcomeOf, type Run } from '../tourRun';
import { scenarios } from '../scenarios';

const base: Run = {scenario: 'mixed', seed: 2, description: '', duration: 10, expected: [], exact_cart: true,
  review_required: false, expected_review: false, passed: true, notes: [],
  steps: [{t: 1, lines: [{sku: 'A', name: 'A', quantity: 1}]}, {t: 4, lines: [{sku: 'A', name: 'A', quantity: 2}]}]};

describe('cartAt', () => {
  it('shows the latest step at or before the video time', () => {
    expect(cartAt(base, 0.5, false)).toEqual([]);
    expect(cartAt(base, 1, false)[0].quantity).toBe(1);
    expect(cartAt(base, 3.9, false)[0].quantity).toBe(1);
    expect(cartAt(base, 4, false)[0].quantity).toBe(2);
  });
  it('shows the final cart once the video has ended, whatever the time', () => {
    expect(cartAt(base, 0, true)[0].quantity).toBe(2);
  });
  it('is empty before a run has loaded', () => {
    expect(cartAt(null, 5, true)).toEqual([]);
  });
});

describe('outcomeOf and endingOf', () => {
  it('separates automatic closes, correct hand-offs, unnecessary hand-offs and wrong closes', () => {
    expect(outcomeOf(null)).toBeNull();
    expect(outcomeOf(base)?.title).toBe('Closed automatically, exactly right');
    expect(endingOf(base)).toBe('pass');
    const held = {...base, review_required: true, expected_review: true};
    expect(outcomeOf(held)?.title).toBe('Correctly held for an associate');
    expect(endingOf(held)).toBe('held');
    const assist = {...base, passed: false, review_required: true};
    expect(outcomeOf(assist)?.tone).toBe('assist');
    expect(outcomeOf(assist)?.text).toMatch(/cart was right/);
    expect(outcomeOf({...assist, exact_cart: false})?.text).toMatch(/could not settle/);
    expect(endingOf(assist)).toBe('assist');
    const wrong = {...base, passed: false, exact_cart: false};
    expect(outcomeOf(wrong)?.tone).toBe('fail');
    expect(endingOf(wrong)).toBe('fail');
  });
  it('reads every published tour run', () => {
    for (const s of scenarios) {
      const run = JSON.parse(readFileSync(resolve(__dirname, `../../public/tour/${s.id}.json`), 'utf8')) as Run;
      expect(run.scenario).toBe(s.id);
      expect(outcomeOf(run)).not.toBeNull();
      expect(Array.isArray(cartAt(run, run.duration, true))).toBe(true);
    }
  });
});
