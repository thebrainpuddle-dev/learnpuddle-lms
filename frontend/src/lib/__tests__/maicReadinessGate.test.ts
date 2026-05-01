// src/lib/__tests__/maicReadinessGate.test.ts
//
// F3 (P0) — Two-milestone classroom-ready gating.
//
// `isClassroomPlayable` is the canonical helper that decides whether the
// MAICPlayerPage should hand control to the player (Stage) or keep showing
// the "Finishing up — fetching slide images…" preparing panel.
//
// Two paths share this function:
//
//   1. Legacy fallback (pre-F2 classrooms with no `content_image_tasks`
//      hydrated). The gate degrades to `!images_pending` exactly like the
//      pre-F3 code did, so old rows behave identically.
//
//   2. F2-aware path. When the per-element media-task store has been
//      hydrated for this classroom, we let the user in as soon as **scene
//      0** has all its image elements terminal (`done` or `failed`). This
//      mirrors OpenMAIC's `firstSceneReady` behaviour: users start playing
//      the moment scene 1 is paintable, while remaining scenes stream into
//      place behind the scenes. The classroom-level `images_pending` boolean
//      keeps driving the polling refresh interval and the "Fetching images…"
//      header badge until the WHOLE batch is done — that's intentional and
//      not the gate's concern.
//
// Element keys may arrive in two shapes:
//   - plain     → `<sceneIdx>:<slideIdx>:<elementIdx>:<elementId>`
//   - walker    → `<prefix>:<sceneIdx>:<slideIdx>:<elementIdx>:<elementId>`
//
// (The walker prefix is a stable namespace tag like `meta_slides` that the
// backend stamps when traversing `content_meta.slides`. The frontend store
// treats keys as opaque strings; only the gate parser cares about scene
// position.)

import { describe, test, expect } from 'vitest';
import {
  isClassroomPlayable,
  parseSceneIndexFromElementKey,
} from '../maicReadinessGate';
import type { ContentImageTasksMap } from '../../stores/maicMediaGenerationStore';

// ─── parseSceneIndexFromElementKey ──────────────────────────────────────────

describe('parseSceneIndexFromElementKey', () => {
  test('parses plain 4-part key — uses index 0', () => {
    expect(parseSceneIndexFromElementKey('0:1:2:img-meta-0')).toBe(0);
    expect(parseSceneIndexFromElementKey('5:0:0:hero')).toBe(5);
  });

  test('parses walker-prefixed 5-part key — uses index 1', () => {
    expect(parseSceneIndexFromElementKey('meta_slides:0:0:0:img-meta-0')).toBe(0);
    expect(parseSceneIndexFromElementKey('meta_slides:3:1:2:hero')).toBe(3);
  });

  test('returns null for unparseable keys', () => {
    expect(parseSceneIndexFromElementKey('')).toBeNull();
    expect(parseSceneIndexFromElementKey('only:two')).toBeNull();
    expect(parseSceneIndexFromElementKey('a:b:c:d')).toBeNull(); // non-numeric
  });
});

// ─── isClassroomPlayable — legacy fallback (empty task map) ─────────────────

describe('isClassroomPlayable — legacy path (no content_image_tasks)', () => {
  test('empty task map + images_pending=true → not playable', () => {
    expect(
      isClassroomPlayable({ tasks: {}, imagesPending: true }),
    ).toBe(false);
  });

  test('empty task map + images_pending=false → playable', () => {
    expect(
      isClassroomPlayable({ tasks: {}, imagesPending: false }),
    ).toBe(true);
  });

  test('empty task map + images_pending undefined → NOT playable (R5 strict contract)', () => {
    // R5 (2026-04-29) tightened the gate from `imagesPending !== true` to
    // `imagesPending === false`. Rationale: the backend serializer
    // (`backend/apps/courses/maic_views.py:1016` for teacher,
    // `:1938` for student) always emits `images_pending` as an explicit
    // boolean — the underlying field is `BooleanField(default=False)` (see
    // `backend/apps/courses/maic_models.py:284-290` and migration
    // `0042_classroom_images_pending`), which is non-nullable with a
    // concrete default. So `undefined` should NEVER reach this gate from
    // the wire in practice.
    //
    // If `undefined` does sneak through (mocked test fixture, partial
    // hydration, JS bug), we now FAIL CLOSED — keep the prep spinner up
    // rather than risk dumping a user into a half-rendered Stage. This is
    // the deliberate semantics change FX-1 ratifies.
    expect(
      isClassroomPlayable({ tasks: {}, imagesPending: undefined }),
    ).toBe(false);
  });
});

// ─── isClassroomPlayable — F2-aware (per-element tasks present) ─────────────

describe('isClassroomPlayable — F3 first-scene-ready path', () => {
  test('scene 0 has 2 images both pending → not playable (still waiting)', () => {
    const tasks: ContentImageTasksMap = {
      '0:0:0:img-a': { status: 'pending' },
      '0:0:1:img-b': { status: 'pending' },
    };
    expect(
      isClassroomPlayable({ tasks, imagesPending: true }),
    ).toBe(false);
  });

  test('scene 0 has 2 images both done → playable (F3 win)', () => {
    const tasks: ContentImageTasksMap = {
      '0:0:0:img-a': { status: 'done', src: 'a.png' },
      '0:0:1:img-b': { status: 'done', src: 'b.png' },
    };
    // images_pending stays TRUE because scene 1+ are still generating —
    // the F3 win is letting the user in anyway.
    expect(
      isClassroomPlayable({ tasks, imagesPending: true }),
    ).toBe(true);
  });

  test('scene 0 has 1 done + 1 failed → playable (failed counts as terminal)', () => {
    const tasks: ContentImageTasksMap = {
      '0:0:0:img-a': { status: 'done', src: 'a.png' },
      '0:0:1:img-b': { status: 'failed', error_code: 'PROVIDER_DISABLED' },
    };
    expect(
      isClassroomPlayable({ tasks, imagesPending: true }),
    ).toBe(true);
  });

  test('scene 0 has 1 done + 1 generating → not playable', () => {
    const tasks: ContentImageTasksMap = {
      '0:0:0:img-a': { status: 'done', src: 'a.png' },
      '0:0:1:img-b': { status: 'generating' },
    };
    expect(
      isClassroomPlayable({ tasks, imagesPending: true }),
    ).toBe(false);
  });

  test('walker-prefixed keys are parsed correctly', () => {
    const tasks: ContentImageTasksMap = {
      'meta_slides:0:0:0:img-a': { status: 'done', src: 'a.png' },
      'meta_slides:0:0:1:img-b': { status: 'done', src: 'b.png' },
      // Scene 5 still pending — must not affect the gate.
      'meta_slides:5:0:0:img-late': { status: 'pending' },
    };
    expect(
      isClassroomPlayable({ tasks, imagesPending: true }),
    ).toBe(true);
  });

  test('scene 0 has zero image elements (only scene 5 has tasks) → playable immediately', () => {
    const tasks: ContentImageTasksMap = {
      '5:0:0:img-late': { status: 'pending' },
      '5:0:1:img-late-2': { status: 'generating' },
    };
    expect(
      isClassroomPlayable({ tasks, imagesPending: true }),
    ).toBe(true);
  });

  test('mixed walker and plain keys for scene 0 — both must be terminal', () => {
    const tasks: ContentImageTasksMap = {
      'meta_slides:0:0:0:a': { status: 'done', src: 'a.png' },
      '0:0:1:b': { status: 'pending' }, // still pending
    };
    expect(
      isClassroomPlayable({ tasks, imagesPending: true }),
    ).toBe(false);
  });

  test('unparseable key in task map is ignored (does not block)', () => {
    const tasks: ContentImageTasksMap = {
      'totally:bogus:key': { status: 'pending' },
      '0:0:0:img-a': { status: 'done', src: 'a.png' },
    };
    expect(
      isClassroomPlayable({ tasks, imagesPending: true }),
    ).toBe(true);
  });

  test('F2 path overrides legacy: scene 0 ready + images_pending=true → playable', () => {
    // The whole point of F3: don't wait for the global flag.
    const tasks: ContentImageTasksMap = {
      '0:0:0:img-a': { status: 'done', src: 'a.png' },
    };
    expect(
      isClassroomPlayable({ tasks, imagesPending: true }),
    ).toBe(true);
  });

  test('F2 path: scene 0 still pending + images_pending=false → playable (legacy wins)', () => {
    // If the global flag says everything's done, trust it — the per-element
    // map may be a stale hydration. Don't lock the user out.
    const tasks: ContentImageTasksMap = {
      '0:0:0:img-a': { status: 'pending' },
    };
    expect(
      isClassroomPlayable({ tasks, imagesPending: false }),
    ).toBe(true);
  });
});
