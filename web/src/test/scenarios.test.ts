import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { scenarioName, scenarios } from '../scenarios';

const repo = resolve(__dirname, '../../..');

describe('scenarios', () => {
  it('lists the same scenarios as the API', () => {
    const store = readFileSync(resolve(repo, 'api/store.py'), 'utf8');
    const block = store.match(/SCENARIOS = \{([^}]*)\}/);
    expect(block).not.toBeNull();
    const api = [...block![1].matchAll(/"([a-z]+)"/g)].map(m => m[1]).sort();
    expect(scenarios.map(s => s.id).sort()).toEqual(api);
  });
  it('has unique IDs and a recorded tour run and thumbnail for every scenario', () => {
    expect(new Set(scenarios.map(s => s.id)).size).toBe(scenarios.length);
    for (const s of scenarios) {
      expect(existsSync(resolve(repo, `web/public/tour/${s.id}.json`)), `tour/${s.id}.json`).toBe(true);
      expect(existsSync(resolve(repo, `web/public/scenarios/${s.id}.jpg`)), `scenarios/${s.id}.jpg`).toBe(true);
    }
  });
  it('names scenarios by ID and falls back to the ID or a dash', () => {
    expect(scenarioName('lumber')).toBe('Lumber');
    expect(scenarioName('not-a-scenario')).toBe('not-a-scenario');
    expect(scenarioName()).toBe('—');
  });
});
