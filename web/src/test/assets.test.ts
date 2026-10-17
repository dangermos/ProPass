import { describe, expect, it } from 'vitest';
import { asset } from '../assets';

describe('asset', () => {
  it('resolves public files against the base URL, with or without a leading slash', () => {
    const base = import.meta.env.BASE_URL;
    expect(asset('tour/single.json')).toBe(`${base}tour/single.json`);
    expect(asset('/results.json')).toBe(`${base}results.json`);
  });
});
