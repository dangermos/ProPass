import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { precaution, type Split } from '../results';

const repo = resolve(__dirname, '../../..');
const results = JSON.parse(readFileSync(resolve(repo, 'web/public/results.json'), 'utf8')) as {test: Split; dev: Split};

describe('precautionary hand-offs', () => {
  it('adds up: by-design hand-offs, automatic closes, precautionary hand-offs and wrong closes cover every run', () => {
    const t = results.test;
    expect(t.held + t.auto + t.extra + t.wrong).toBe(t.runs);
    expect(t.extra_incomplete).toBeLessThanOrEqual(t.extra);
  });
  it('words the split exactly as the generated README does', () => {
    const readme = readFileSync(resolve(repo, 'README.md'), 'utf8');
    expect(readme).toContain(precaution(results.test));
  });
  it('drops the overcharge clause when no cart had an extra item', () => {
    expect(precaution(results.dev)).not.toMatch(/overcharged/);
    expect(precaution(results.dev)).toMatch(/undercharged/);
  });
});
