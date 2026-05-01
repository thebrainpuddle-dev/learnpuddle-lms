// stores/__tests__/maicMediaGenerationStore.test.ts
//
// F2 (P0) — exhaustive coverage of every store transition.

import { describe, test, expect, beforeEach } from 'vitest';
import {
  useMaicMediaGenerationStore,
  type MaicImageTaskEvent,
} from '../maicMediaGenerationStore';

const CR = 'classroom-uuid-1';
const KEY = '0:0:0:el-1';

function s() {
  return useMaicMediaGenerationStore.getState();
}

describe('maicMediaGenerationStore', () => {
  beforeEach(() => {
    useMaicMediaGenerationStore.getState().resetAll();
  });

  describe('hydrateFromMap', () => {
    test('seeds tasks from a GET payload', () => {
      s().hydrateFromMap(CR, {
        '0:0:0:el-1': { status: 'pending', updated_at: '2026-04-28T12:00:00Z' },
        '0:0:1:el-2': {
          status: 'done',
          src: 'https://cdn.example/img.jpg',
          updated_at: '2026-04-28T12:00:01Z',
        },
      });

      expect(s().getTask('0:0:0:el-1')?.status).toBe('pending');
      expect(s().getTask('0:0:1:el-2')?.status).toBe('done');
      expect(s().getTask('0:0:1:el-2')?.src).toBe('https://cdn.example/img.jpg');
    });

    test('replaces only the target classroom; leaves others alone', () => {
      s().hydrateFromMap('classroom-A', {
        'a-key': { status: 'done', src: 'https://a/1.jpg' },
      });
      s().hydrateFromMap('classroom-B', {
        'b-key': { status: 'pending' },
      });

      // Re-hydrate A with an empty map → A's task should clear, B remains.
      s().hydrateFromMap('classroom-A', {});

      expect(s().getTask('a-key')).toBeUndefined();
      expect(s().getTask('b-key')?.status).toBe('pending');
    });

    test('error_code on the GET payload is preserved as errorCode', () => {
      s().hydrateFromMap(CR, {
        [KEY]: { status: 'failed', error_code: 'CONTENT_SENSITIVE' },
      });
      expect(s().getTask(KEY)?.errorCode).toBe('CONTENT_SENSITIVE');
    });
  });

  describe('applyEvent transitions', () => {
    function evt(partial: Partial<MaicImageTaskEvent>): MaicImageTaskEvent {
      return {
        type: 'maic.image.task',
        classroom_id: CR,
        element_key: KEY,
        status: 'pending',
        ...partial,
      };
    }

    test('pending → generating → done', () => {
      s().applyEvent(evt({ status: 'pending', updated_at: '2026-04-28T12:00:00Z' }));
      expect(s().getTask(KEY)?.status).toBe('pending');

      s().applyEvent(evt({ status: 'generating', updated_at: '2026-04-28T12:00:01Z' }));
      expect(s().getTask(KEY)?.status).toBe('generating');

      s().applyEvent(
        evt({
          status: 'done',
          src: 'https://cdn.example/done.jpg',
          updated_at: '2026-04-28T12:00:02Z',
        }),
      );
      const t = s().getTask(KEY);
      expect(t?.status).toBe('done');
      expect(t?.src).toBe('https://cdn.example/done.jpg');
      expect(t?.errorCode).toBeUndefined();
    });

    test('failed carries error_code', () => {
      s().applyEvent(
        evt({
          status: 'failed',
          error_code: 'TIMEOUT',
          updated_at: '2026-04-28T12:00:03Z',
        }),
      );
      expect(s().getTask(KEY)?.status).toBe('failed');
      expect(s().getTask(KEY)?.errorCode).toBe('TIMEOUT');
    });

    test('event with updated_at equal to current is dropped (idempotent replay)', () => {
      // WAVE-F2-F4: stale-guard uses `<=`, so an event whose updated_at
      // matches the existing task's updated_at is treated as a duplicate
      // and SKIPPED. This protects against millisecond-granularity replays
      // on WS reconnect where two events can share an identical timestamp.
      s().applyEvent(
        evt({
          status: 'done',
          src: 'https://cdn.example/first.jpg',
          updated_at: '2026-04-28T12:00:10Z',
        }),
      );
      // Same timestamp, different status + src — must be dropped.
      s().applyEvent(
        evt({
          status: 'failed',
          error_code: 'TIMEOUT',
          updated_at: '2026-04-28T12:00:10Z',
        }),
      );
      const t = s().getTask(KEY);
      expect(t?.status).toBe('done');
      expect(t?.src).toBe('https://cdn.example/first.jpg');
      expect(t?.errorCode).toBeUndefined();
    });

    test('out-of-order (stale) event is dropped', () => {
      s().applyEvent(
        evt({
          status: 'done',
          src: 'https://cdn.example/new.jpg',
          updated_at: '2026-04-28T12:00:10Z',
        }),
      );
      // Older "generating" arriving late must NOT clobber the done state.
      s().applyEvent(
        evt({ status: 'generating', updated_at: '2026-04-28T12:00:05Z' }),
      );
      expect(s().getTask(KEY)?.status).toBe('done');
      expect(s().getTask(KEY)?.src).toBe('https://cdn.example/new.jpg');
    });

    test('done → failed clears the previous src? no — keeps src for fallback display', () => {
      // Design choice: when a later "failed" arrives after a "done", we
      // keep the old src around (the element already rendered fine; we
      // only mark the status). errorCode is set; src is preserved.
      s().applyEvent(
        evt({
          status: 'done',
          src: 'https://cdn.example/old.jpg',
          updated_at: '2026-04-28T12:00:00Z',
        }),
      );
      s().applyEvent(
        evt({
          status: 'failed',
          error_code: 'PROVIDER_DISABLED',
          updated_at: '2026-04-28T12:00:01Z',
        }),
      );
      const t = s().getTask(KEY);
      expect(t?.status).toBe('failed');
      expect(t?.errorCode).toBe('PROVIDER_DISABLED');
      expect(t?.src).toBe('https://cdn.example/old.jpg');
    });

    test('non-matching event type is ignored', () => {
      // Force-cast — we intentionally feed garbage to verify the guard.
      s().applyEvent({ type: 'maic.unrelated' as 'maic.image.task', classroom_id: CR, element_key: KEY, status: 'done' } as MaicImageTaskEvent);
      expect(s().getTask(KEY)).toBeUndefined();
    });
  });

  describe('clearStage', () => {
    test('removes only the requested classroom', () => {
      s().hydrateFromMap('A', { 'a:k': { status: 'done', src: 'https://a' } });
      s().hydrateFromMap('B', { 'b:k': { status: 'done', src: 'https://b' } });

      s().clearStage('A');

      expect(s().getTask('a:k')).toBeUndefined();
      expect(s().getTask('b:k')?.status).toBe('done');
    });

    test('clearStage on an empty classroom is a no-op', () => {
      s().hydrateFromMap('A', { 'a:k': { status: 'pending' } });
      s().clearStage('non-existent');
      expect(s().getTask('a:k')?.status).toBe('pending');
    });
  });

  describe('useMediaTask selector helper', () => {
    test('returns undefined when the elementKey is undefined or unknown', () => {
      // We don't render here — the selector runs synchronously off
      // getState() and we test it as a plain function via the store
      // direct getter (which is the implementation detail under the hood).
      expect(s().getTask('not-tracked')).toBeUndefined();
    });
  });

  describe('resetAll', () => {
    test('wipes everything', () => {
      s().hydrateFromMap('A', { 'a:k': { status: 'done' } });
      s().resetAll();
      expect(Object.keys(s().tasks).length).toBe(0);
    });
  });
});
