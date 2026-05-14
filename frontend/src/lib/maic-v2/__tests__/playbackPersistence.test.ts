/**
 * Tests for playbackPersistence — localStorage-backed PlaybackSnapshot
 * save/restore. Vitest + jsdom; localStorage is a real implementation
 * in jsdom so no mocks are needed.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  createPlaybackPersistence,
  type PlaybackPersistence,
} from '../playbackPersistence';
import type { PlaybackSnapshot } from '../playback-types';


const SAMPLE: PlaybackSnapshot = {
  sceneIndex: 2,
  actionIndex: 7,
  consumedDiscussions: ['disc-1', 'disc-3'],
  sceneId: 'scene-abc',
};


describe('playbackPersistence', () => {
  beforeEach(() => {
    // happy-dom's `clear()` proto method isn't reliably present —
    // iterate + remove to keep the test independent of that quirk.
    const keys: string[] = [];
    for (let i = 0; i < window.localStorage.length; i++) {
      const k = window.localStorage.key(i);
      if (k !== null) keys.push(k);
    }
    keys.forEach((k) => window.localStorage.removeItem(k));
  });

  afterEach(() => {
    // happy-dom's `clear()` proto method isn't reliably present —
    // iterate + remove to keep the test independent of that quirk.
    const keys: string[] = [];
    for (let i = 0; i < window.localStorage.length; i++) {
      const k = window.localStorage.key(i);
      if (k !== null) keys.push(k);
    }
    keys.forEach((k) => window.localStorage.removeItem(k));
  });

  // ── save + load round-trip ───────────────────────────────────────

  describe('save + load round-trip', () => {
    it('persists and reads back a snapshot for a given sessionId', () => {
      const p = createPlaybackPersistence('session-A');
      p.save(SAMPLE);
      expect(p.load()).toEqual(SAMPLE);
    });

    it('isolates snapshots between distinct sessionIds', () => {
      const a = createPlaybackPersistence('session-A');
      const b = createPlaybackPersistence('session-B');
      a.save(SAMPLE);
      expect(b.load()).toBeNull();
      expect(a.load()).toEqual(SAMPLE);
    });

    it('overwrites the previous snapshot (last write wins)', () => {
      const p = createPlaybackPersistence('session-A');
      p.save(SAMPLE);
      const newer: PlaybackSnapshot = {
        ...SAMPLE,
        actionIndex: 12,
      };
      p.save(newer);
      expect(p.load()).toEqual(newer);
    });

    it('two handles for the same sessionId share storage', () => {
      const a = createPlaybackPersistence('session-A');
      const b = createPlaybackPersistence('session-A');
      a.save(SAMPLE);
      expect(b.load()).toEqual(SAMPLE);
    });
  });

  // ── empty sessionId no-op ────────────────────────────────────────

  describe('empty sessionId no-op guard', () => {
    it('save with empty sessionId does not write to localStorage', () => {
      const p = createPlaybackPersistence('');
      p.save(SAMPLE);
      // No keys should be set anywhere
      expect(window.localStorage.length).toBe(0);
    });

    it('load with empty sessionId returns null', () => {
      const p = createPlaybackPersistence('');
      expect(p.load()).toBeNull();
    });

    it('clear with empty sessionId is a no-op', () => {
      window.localStorage.setItem('unrelated-key', 'unrelated-value');
      const p = createPlaybackPersistence('');
      p.clear();
      // The unrelated key must survive.
      expect(window.localStorage.getItem('unrelated-key')).toBe('unrelated-value');
    });
  });

  // ── corrupted entry self-cleanup ─────────────────────────────────

  describe('corrupted entry handling', () => {
    it('returns null and clears a malformed JSON entry', () => {
      window.localStorage.setItem('maic-v2:playback:session-A', '{not valid json');
      const p = createPlaybackPersistence('session-A');
      expect(p.load()).toBeNull();
      // Entry is dropped so subsequent loads don't keep retrying it.
      expect(window.localStorage.getItem('maic-v2:playback:session-A')).toBeNull();
    });

    it('returns null and clears an entry missing required fields', () => {
      window.localStorage.setItem(
        'maic-v2:playback:session-A',
        JSON.stringify({ sceneIndex: 1 }),
      );
      const p = createPlaybackPersistence('session-A');
      expect(p.load()).toBeNull();
      expect(window.localStorage.getItem('maic-v2:playback:session-A')).toBeNull();
    });

    it('returns null and clears an entry with non-array consumedDiscussions', () => {
      window.localStorage.setItem(
        'maic-v2:playback:session-A',
        JSON.stringify({
          sceneIndex: 1,
          actionIndex: 2,
          consumedDiscussions: 'not-an-array',
        }),
      );
      const p = createPlaybackPersistence('session-A');
      expect(p.load()).toBeNull();
    });
  });

  // ── clear ────────────────────────────────────────────────────────

  describe('clear', () => {
    it('removes the persisted snapshot', () => {
      const p = createPlaybackPersistence('session-A');
      p.save(SAMPLE);
      expect(p.load()).toEqual(SAMPLE);
      p.clear();
      expect(p.load()).toBeNull();
    });

    it('does not affect other sessionIds', () => {
      const a = createPlaybackPersistence('session-A');
      const b = createPlaybackPersistence('session-B');
      a.save(SAMPLE);
      b.save(SAMPLE);
      a.clear();
      expect(a.load()).toBeNull();
      expect(b.load()).toEqual(SAMPLE);
    });
  });

  // ── quota / errors swallowed ─────────────────────────────────────

  describe('quota / error resilience', () => {
    it('save swallows storage exceptions and never throws', () => {
      const originalStringify = JSON.stringify;
      JSON.stringify = () => {
        throw new DOMException('quota exceeded', 'QuotaExceededError');
      };
      const consoleWarnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
      try {
        const p: PlaybackPersistence = createPlaybackPersistence('session-A');
        expect(() => p.save(SAMPLE)).not.toThrow();
        expect(consoleWarnSpy).toHaveBeenCalled();
      } finally {
        JSON.stringify = originalStringify;
        consoleWarnSpy.mockRestore();
      }
    });

    it('clear swallows storage exceptions and never throws', () => {
      const originalStorage = window.localStorage;
      const throwingStorage = Object.create(originalStorage) as Storage;
      Object.defineProperty(throwingStorage, 'removeItem', {
        configurable: true,
        value: () => {
          throw new Error('boom');
        },
      });
      Object.defineProperty(window, 'localStorage', {
        configurable: true,
        value: throwingStorage,
      });
      try {
        const p = createPlaybackPersistence('session-A');
        expect(() => p.clear()).not.toThrow();
      } finally {
        Object.defineProperty(window, 'localStorage', {
          configurable: true,
          value: originalStorage,
        });
      }
    });
  });

  // ── shape lock ───────────────────────────────────────────────────

  describe('storage shape', () => {
    it('uses the documented key shape: maic-v2:playback:${sessionId}', () => {
      const p = createPlaybackPersistence('my-session-123');
      p.save(SAMPLE);
      // Key should appear verbatim — locked so future deploys don't
      // silently break stored snapshots.
      expect(window.localStorage.getItem('maic-v2:playback:my-session-123')).not
        .toBeNull();
    });

    it('preserves all PlaybackSnapshot fields including optional sceneId', () => {
      const p = createPlaybackPersistence('session-A');
      const withScene: PlaybackSnapshot = {
        sceneIndex: 5,
        actionIndex: 3,
        consumedDiscussions: [],
        sceneId: 'scene-xyz',
      };
      p.save(withScene);
      const loaded = p.load();
      expect(loaded?.sceneId).toBe('scene-xyz');
    });

    it('round-trips a snapshot without sceneId (optional field)', () => {
      const p = createPlaybackPersistence('session-A');
      const noScene: PlaybackSnapshot = {
        sceneIndex: 0,
        actionIndex: 0,
        consumedDiscussions: [],
      };
      p.save(noScene);
      const loaded = p.load();
      expect(loaded).toEqual(noScene);
      expect(loaded?.sceneId).toBeUndefined();
    });
  });
});
