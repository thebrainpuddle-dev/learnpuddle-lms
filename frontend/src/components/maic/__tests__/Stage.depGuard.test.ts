// Stage.depGuard.test.ts
//
// TEST-P0-6-F1 — Structural guard on Stage.tsx's scene-load useEffect dep array.
//
// WHY THIS EXISTS
// ---------------
// TEST-P0-6 added a proxy unit test (Stage.renderLoop.test.tsx, 4 tests) that
// exercises the exact same store-subscription → useMemo → id-keyed-effect
// pattern used in Stage.tsx. That proxy test passes GREEN even if the real
// Stage.tsx quietly regresses back to the buggy dependency array, because
// Stage is too expensive to render in a unit test (engine, IndexedDB, PiP,
// the whole playback-engine graph, etc.).
//
// This file fills that gap with a cheap grep/regex scan of the Stage.tsx
// source text. It cannot be silenced by a passing proxy — it reads the
// production file directly. Any revert of the fix trips the test immediately.
//
// The bug pattern being guarded:
//
//   // BUGGY (pre-fix):
//   useEffect(() => {
//     if (currentScene) loadScene(currentScene);
//   }, [currentScene]);          ← bare object, re-fires on every refetch
//
//   // CORRECT (post-fix):
//   useEffect(() => {
//     if (currentScene) loadScene(currentScene);
//   }, [currentScene?.id, loadScene]);  ← stable primitive + stable callback ref
//
// Reference: Stage.tsx lines ~213-221 (see comment block starting
// "Load scene actions when scene changes").
//
// See also: Stage.renderLoop.test.tsx (TEST-P0-6) for the behavioural proof.

import * as fs from 'fs';
import * as path from 'path';
import { describe, test, expect } from 'vitest';

// ---------------------------------------------------------------------------
// Load source
// ---------------------------------------------------------------------------

const STAGE_PATH = path.resolve(__dirname, '../Stage.tsx');
const source = fs.readFileSync(STAGE_PATH, 'utf8');

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Extract the substring of `source` that starts at the first `useEffect`
 * whose body contains `loadScene(` and ends at the next line that contains
 * the dep array closing `]`. We look for the closing `}, [` pattern that
 * follows the effect body, then read until the `;` on the same line.
 *
 * Returns the dep array literal substring, e.g. `[currentScene?.id, loadScene]`.
 */
function extractLoadSceneDepArray(src: string): string | null {
  // Find the position of the useEffect that calls loadScene.
  const effectStart = src.search(/useEffect\s*\(\s*\(\s*\)\s*=>\s*\{[^}]*loadScene\s*\(/s);
  if (effectStart === -1) return null;

  // From that position, look for the closing `}, [...]` dep array.
  const afterEffect = src.slice(effectStart);
  const depArrayMatch = afterEffect.match(/},\s*\[([^\]]*)\]\s*\)/s);
  if (!depArrayMatch) return null;

  return depArrayMatch[0]; // includes the `}, [...]` wrapper
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('Stage.tsx scene-load useEffect dep array (TEST-P0-6-F1 structural guard)', () => {
  test('Stage.tsx exists and is readable', () => {
    expect(source.length, `Could not read ${STAGE_PATH}`).toBeGreaterThan(0);
  });

  test('dep array contains "currentScene?.id" — stable primitive, not the full object', () => {
    const depBlock = extractLoadSceneDepArray(source);
    expect(
      depBlock,
      'Could not locate the loadScene useEffect dep array in Stage.tsx. ' +
        'Did the effect move or get renamed?',
    ).not.toBeNull();

    expect(
      depBlock,
      'REGRESSION: dep array no longer contains "currentScene?.id". ' +
        'The fix in TEST-P0-6 has been reverted — Stage.tsx will re-fire ' +
        'loadScene on every React-Query refetch and trigger a render loop.',
    ).toContain('currentScene?.id');
  });

  test('dep array contains "loadScene" — callback ref included to satisfy exhaustive-deps', () => {
    const depBlock = extractLoadSceneDepArray(source);
    expect(
      depBlock,
      'Could not locate the loadScene useEffect dep array in Stage.tsx.',
    ).not.toBeNull();

    expect(
      depBlock,
      'REGRESSION: dep array no longer contains "loadScene". ' +
        'The effect may be silently skipping stale-closure updates.',
    ).toContain('loadScene');
  });

  test('dep array does NOT contain bare "currentScene" (object reference — the bug pattern)', () => {
    const depBlock = extractLoadSceneDepArray(source);
    expect(
      depBlock,
      'Could not locate the loadScene useEffect dep array in Stage.tsx.',
    ).not.toBeNull();

    // Pattern: `[currentScene,` or `[currentScene]` or `currentScene,` or `, currentScene]`
    // — i.e. the bare identifier followed by comma or closing bracket, optionally with
    // leading/trailing whitespace. This is the exact bug shape that caused the
    // "Maximum update depth exceeded" loop.
    const bugPattern = /\[\s*currentScene\s*[,\]]/;
    expect(
      bugPattern.test(depBlock!),
      'REGRESSION: dep array matches the bug pattern /[\\s*currentScene\\s*[,\\]]/ — ' +
        'bare `currentScene` object is in the dep array. ' +
        'This will re-fire loadScene on every React-Query refetch (new array reference ' +
        '→ new object reference → effect fires → setState → re-render → loop). ' +
        'Fix: change to [currentScene?.id, loadScene].',
    ).toBe(false);
  });
});
