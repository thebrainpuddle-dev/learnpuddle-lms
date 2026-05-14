/**
 * Tests for src/config/featureFlags.ts.
 *
 * Vitest exposes vi.stubEnv() to override import.meta.env at runtime,
 * which is what we use to drive the `parseFlag` truthy/falsy table.
 * Module is re-imported per test to pick up the stubbed env (Vite
 * caches the module otherwise).
 */
import { describe, test, expect, beforeEach, vi } from 'vitest';

describe('featureFlags', () => {
  beforeEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  test.each([
    ['true', true],
    ['1', true],
    ['yes', true],
    ['ON', true],
    ['TRUE', true],
    ['false', false],
    ['0', false],
    ['no', false],
    ['', false],
    ['anything-else', false],
  ])('VITE_MAIC_V2_ENABLED=%s → maicV2Enabled=%s', async (value, expected) => {
    vi.stubEnv('VITE_MAIC_V2_ENABLED', value);
    const mod = await import('../featureFlags');
    expect(mod.featureFlags.maicV2Enabled).toBe(expected);
  });

  test.each([
    ['true', true],
    ['1', true],
    ['false', false],
    ['', false],
  ])('VITE_MAIC_GENERATION_USE_V2=%s → maicGenerationUseV2=%s', async (value, expected) => {
    vi.stubEnv('VITE_MAIC_GENERATION_USE_V2', value);
    const mod = await import('../featureFlags');
    expect(mod.featureFlags.maicGenerationUseV2).toBe(expected);
  });

  test('undefined env values keep v2 kill-switch off but generation v2-first', async () => {
    vi.stubEnv('VITE_MAIC_V2_ENABLED', undefined as unknown as string);
    vi.stubEnv('VITE_MAIC_GENERATION_USE_V2', undefined as unknown as string);
    const mod = await import('../featureFlags');
    expect(mod.featureFlags.maicV2Enabled).toBe(false);
    expect(mod.featureFlags.maicGenerationUseV2).toBe(true);
  });
});
