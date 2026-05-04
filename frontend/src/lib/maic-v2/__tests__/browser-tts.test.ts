/**
 * Tests for browser-tts.ts (MAIC-413.1).
 *
 * Two slices:
 *   1. `chunkUtterance` — pure function, fully testable in vitest.
 *   2. `createBrowserTTSPlayer` — only the `isAvailable() === false`
 *      branch is testable in happy-dom (no `window.speechSynthesis`).
 *      The full speechSynthesis integration is validated by the
 *      headless Chromium smoke at session close.
 *
 * Per project hard rule: NO mocks of `speechSynthesis`. We don't
 * stand up a fake; instead, the real `isAvailable()` returns false in
 * jsdom/happy-dom, and we verify the fall-through contract (caller's
 * onEnded fires exactly once even when the runtime has no TTS).
 */
import { describe, expect, it } from 'vitest';

import {
  chunkUtterance,
  createBrowserTTSPlayer,
} from '../browser-tts';


// ── chunkUtterance — pure function ────────────────────────────────


describe('chunkUtterance', () => {
  describe('empty + edge cases', () => {
    it('returns [] for empty string', () => {
      expect(chunkUtterance('')).toEqual([]);
    });

    it('returns [] for whitespace-only string', () => {
      expect(chunkUtterance('   \n\t ')).toEqual([]);
    });

    it('returns the original (trimmed) for sub-cap text', () => {
      expect(chunkUtterance('  hello world  ')).toEqual(['hello world']);
    });

    it('keeps a single sentence at maxChars boundary intact', () => {
      const text = 'a'.repeat(120);
      expect(chunkUtterance(text, 120)).toEqual([text]);
    });

    it('returns the trimmed text when maxChars is 0 (defensive)', () => {
      expect(chunkUtterance('hello', 0)).toEqual(['hello']);
    });
  });

  describe('sentence-boundary splitting (pass 1)', () => {
    it('splits on . and keeps the period attached', () => {
      const out = chunkUtterance(
        'First sentence. Second sentence. Third.',
        100,
      );
      expect(out).toEqual([
        'First sentence.',
        'Second sentence.',
        'Third.',
      ]);
    });

    it('splits on ! and ?', () => {
      const out = chunkUtterance('Hey! What is this? Confusing.', 100);
      expect(out).toEqual(['Hey!', 'What is this?', 'Confusing.']);
    });

    it('splits on CJK terminators 。！？', () => {
      const out = chunkUtterance('你好。这是什么？没问题！', 100);
      expect(out).toEqual(['你好。', '这是什么？', '没问题！']);
    });

    it('does NOT split if no terminators present and text fits', () => {
      expect(chunkUtterance('a short fragment', 100)).toEqual([
        'a short fragment',
      ]);
    });
  });

  describe('clause-boundary splitting (pass 2)', () => {
    it('falls back to comma-split when a sentence exceeds maxChars', () => {
      const longSentence = 'when the cat is away the mice will play, but the cat'
        + ' will eventually return and find them, then chaos ensues.';
      const out = chunkUtterance(longSentence, 60);
      // Each chunk should be ≤ 60 chars and break at a , or .
      out.forEach((c) => {
        expect(c.length).toBeLessThanOrEqual(60);
      });
      expect(out.length).toBeGreaterThan(1);
    });

    it('splits on ; and :', () => {
      const text = 'aaaaaaaaaaaaaaaaaaaaaa; bbbbbbbbbbbbbbbbbbbbbb: ccccccccc.';
      const out = chunkUtterance(text, 25);
      out.forEach((c) => expect(c.length).toBeLessThanOrEqual(25));
    });
  });

  describe('whitespace-fallback splitting (pass 3)', () => {
    it('splits on whitespace when no clause terminators help', () => {
      // No . , ; : in the input; chunker must use whitespace.
      const text = 'aaa bbb ccc ddd eee fff ggg hhh iii jjj';
      const out = chunkUtterance(text, 15);
      out.forEach((c) => {
        expect(c.length).toBeLessThanOrEqual(15);
      });
      // Joined back with spaces must reproduce the input
      expect(out.join(' ')).toBe(text);
    });
  });

  describe('hard-cut fallback (pass 4)', () => {
    it('hard-cuts a single word that exceeds maxChars', () => {
      const text = 'a'.repeat(250);
      const out = chunkUtterance(text, 100);
      expect(out.length).toBe(3);
      expect(out[0]).toHaveLength(100);
      expect(out[1]).toHaveLength(100);
      expect(out[2]).toHaveLength(50);
    });
  });

  describe('mixed real-world scenarios', () => {
    it('handles a long paragraph with mixed boundaries', () => {
      const para =
        'Photosynthesis is the process by which plants convert light energy '
        + 'into chemical energy. During this process, plants absorb carbon '
        + 'dioxide and water to produce glucose and oxygen. This is the '
        + 'foundation of most food chains on Earth.';
      const out = chunkUtterance(para, 80);
      out.forEach((c) => expect(c.length).toBeLessThanOrEqual(80));
      // Reassembling preserves all content (allowing for whitespace
      // collapse at chunk boundaries).
      const stripped = out.join(' ').replace(/\s+/g, ' ').trim();
      expect(stripped).toBe(para.replace(/\s+/g, ' ').trim());
    });

    it('handles CJK text with mixed punctuation', () => {
      const text = '光合作用是植物把光能转化为化学能的过程。这一过程吸收二氧化碳和水。';
      const out = chunkUtterance(text, 30);
      out.forEach((c) => expect(c.length).toBeLessThanOrEqual(30));
      expect(out.length).toBeGreaterThan(0);
    });
  });

  describe('invariants (regression net)', () => {
    it('every chunk is non-empty and trimmed', () => {
      const out = chunkUtterance(
        '  Sentence one.   Sentence two. Sentence three.  ',
        100,
      );
      out.forEach((c) => {
        expect(c.length).toBeGreaterThan(0);
        expect(c).toBe(c.trim());
      });
    });

    it('no chunk exceeds maxChars under any valid input', () => {
      const inputs = [
        'short',
        'a'.repeat(500),
        'one. two. three.',
        'no boundaries at all just a long stream of words flowing onward',
        '中文。English. 中英文混合! Multi-script?',
      ];
      for (const text of inputs) {
        const out = chunkUtterance(text, 50);
        out.forEach((c, i) => {
          expect(c.length, `chunk ${i} of ${JSON.stringify(text)}`)
            .toBeLessThanOrEqual(50);
        });
      }
    });
  });
});


// ── BrowserTTSPlayer — fall-through path (no speechSynthesis) ──────


describe('BrowserTTSPlayer fall-through (jsdom / happy-dom)', () => {
  it('isAvailable() is false when window.speechSynthesis is missing', () => {
    const player = createBrowserTTSPlayer();
    // happy-dom doesn't expose speechSynthesis; if a future env DOES,
    // this test will need to handle both branches.
    if (typeof window.speechSynthesis === 'undefined') {
      expect(player.isAvailable()).toBe(false);
    } else {
      expect(player.isAvailable()).toBe(true);
    }
  });

  it('isSpeaking() is false when speech engine is unavailable', () => {
    const player = createBrowserTTSPlayer();
    if (!player.isAvailable()) {
      expect(player.isSpeaking()).toBe(false);
    }
  });

  it('speak() invokes onEnded synchronously when unavailable', () => {
    const player = createBrowserTTSPlayer();
    if (player.isAvailable()) {
      // Skip in real-browser environments — can't validate the
      // fall-through branch when the API IS available.
      return;
    }
    let called = 0;
    player.speak('hello', () => {
      called++;
    });
    expect(called).toBe(1);
  });

  it('speak() with empty text still calls onEnded exactly once', () => {
    const player = createBrowserTTSPlayer();
    if (player.isAvailable()) return;
    let called = 0;
    player.speak('', () => {
      called++;
    });
    expect(called).toBe(1);
  });

  it('pause() / resume() / cancel() are safe no-ops when unavailable', () => {
    const player = createBrowserTTSPlayer();
    if (player.isAvailable()) return;
    expect(() => {
      player.pause();
      player.resume();
      player.cancel();
    }).not.toThrow();
  });
});
