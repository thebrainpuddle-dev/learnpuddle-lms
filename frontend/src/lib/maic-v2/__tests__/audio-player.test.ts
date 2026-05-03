/**
 * Tests for src/lib/maic-v2/audio-player.ts.
 *
 * Stubs HTMLAudioElement so tests run in happy-dom without real audio
 * playback.  Covers the public-API contract the playback engine
 * depends on.
 */
import { describe, test, expect, beforeEach, vi } from 'vitest';

import { AudioPlayer, createAudioPlayer, dataUrlForBase64Mp3 } from '../audio-player';


// ── Stub HTMLAudioElement ─────────────────────────────────────────


class FakeAudio {
  static instances: FakeAudio[] = [];

  src: string = '';
  volume: number = 1;
  paused: boolean = true;
  currentTime: number = 0;
  duration: number = 60;
  defaultPlaybackRate: number = 1;
  playbackRate: number = 1;

  private listeners: Record<string, ((e?: unknown) => void)[]> = {};

  constructor() { FakeAudio.instances.push(this); }

  play = vi.fn(async () => {
    this.paused = false;
  });

  pause = vi.fn(() => { this.paused = true; });

  addEventListener = vi.fn((event: string, cb: (e?: unknown) => void) => {
    (this.listeners[event] ||= []).push(cb);
  });

  removeEventListener = vi.fn((event: string, cb: (e?: unknown) => void) => {
    this.listeners[event] = (this.listeners[event] || []).filter((x) => x !== cb);
  });

  /** Test helper: simulate the natural-end event. */
  fireEnded(): void {
    (this.listeners.ended || []).forEach((cb) => cb());
  }
}


beforeEach(() => {
  FakeAudio.instances = [];
  // @ts-expect-error — replacing global Audio constructor
  globalThis.Audio = FakeAudio;
  // URL.createObjectURL / revokeObjectURL stubs (happy-dom may not provide).
  // @ts-expect-error
  globalThis.URL.revokeObjectURL = vi.fn();
});


// ── play() ─────────────────────────────────────────────────────────


describe('AudioPlayer.play', () => {
  test('returns false when no audioUrl provided (no IndexedDB in Phase 1)', async () => {
    const ap = new AudioPlayer();
    const result = await ap.play('audio-1');
    expect(result).toBe(false);
    expect(FakeAudio.instances).toHaveLength(0);
  });

  test('plays from a data: URL', async () => {
    const ap = new AudioPlayer();
    const url = dataUrlForBase64Mp3('aGVsbG8=');  // 'hello' in b64
    const result = await ap.play('audio-1', url);
    expect(result).toBe(true);
    expect(FakeAudio.instances).toHaveLength(1);
    expect(FakeAudio.instances[0].src).toBe(url);
    expect(FakeAudio.instances[0].play).toHaveBeenCalledOnce();
  });

  test('plays from an https URL', async () => {
    const ap = new AudioPlayer();
    await ap.play('audio-2', 'https://cdn.example/audio.mp3');
    expect(FakeAudio.instances[0].src).toBe('https://cdn.example/audio.mp3');
  });

  test('stops prior audio when play() called twice', async () => {
    const ap = new AudioPlayer();
    await ap.play('a1', 'data:audio/mp3;base64,a');
    const first = FakeAudio.instances[0];
    await ap.play('a2', 'data:audio/mp3;base64,b');
    expect(first.pause).toHaveBeenCalled();
    expect(FakeAudio.instances).toHaveLength(2);
  });

  test('applies muted, volume, playbackRate before play', async () => {
    const ap = new AudioPlayer();
    ap.setVolume(0.7);
    ap.setPlaybackRate(1.5);
    await ap.play('a', 'data:audio/mp3;base64,a');
    const audio = FakeAudio.instances[0];
    expect(audio.volume).toBe(0.7);
    expect(audio.playbackRate).toBe(1.5);
  });

  test('rethrows browser playback errors with logged context', async () => {
    const ap = new AudioPlayer();
    // Override the FakeAudio constructor's play to reject
    class Rejecting extends FakeAudio {
      play = vi.fn(async () => { throw new Error('autoplay-blocked'); });
    }
    // @ts-expect-error
    globalThis.Audio = Rejecting;
    await expect(ap.play('a', 'data:audio/mp3;base64,a')).rejects.toThrow(/autoplay-blocked/);
  });
});


// ── pause / resume / stop / state ─────────────────────────────────


describe('AudioPlayer state transitions', () => {
  test('pause() pauses currently-playing audio', async () => {
    const ap = new AudioPlayer();
    await ap.play('a', 'data:audio/mp3;base64,a');
    expect(ap.isPlaying()).toBe(true);
    ap.pause();
    expect(ap.isPlaying()).toBe(false);
    expect(FakeAudio.instances[0].pause).toHaveBeenCalled();
  });

  test('resume() resumes paused audio', async () => {
    const ap = new AudioPlayer();
    await ap.play('a', 'data:audio/mp3;base64,a');
    ap.pause();
    ap.resume();
    // play.mock.calls: 1 from initial play, 1 from resume
    expect(FakeAudio.instances[0].play).toHaveBeenCalledTimes(2);
  });

  test('resume() is a no-op when not paused', async () => {
    const ap = new AudioPlayer();
    await ap.play('a', 'data:audio/mp3;base64,a');
    // Currently playing (not paused); resume should NOT call play() again
    ap.resume();
    expect(FakeAudio.instances[0].play).toHaveBeenCalledTimes(1);
  });

  test('stop() clears the audio reference', async () => {
    const ap = new AudioPlayer();
    await ap.play('a', 'data:audio/mp3;base64,a');
    ap.stop();
    expect(ap.hasActiveAudio()).toBe(false);
    expect(ap.isPlaying()).toBe(false);
  });

  test('hasActiveAudio() true while paused, false after stop', async () => {
    const ap = new AudioPlayer();
    await ap.play('a', 'data:audio/mp3;base64,a');
    ap.pause();
    expect(ap.hasActiveAudio()).toBe(true);
    ap.stop();
    expect(ap.hasActiveAudio()).toBe(false);
  });
});


// ── onEnded callback ──────────────────────────────────────────────


describe('AudioPlayer onEnded', () => {
  test('fires the registered callback when audio reaches natural end', async () => {
    const ap = new AudioPlayer();
    const cb = vi.fn();
    ap.onEnded(cb);
    await ap.play('a', 'data:audio/mp3;base64,a');
    FakeAudio.instances[0].fireEnded();
    expect(cb).toHaveBeenCalledOnce();
  });

  test('latest onEnded registration wins', async () => {
    const ap = new AudioPlayer();
    const oldCb = vi.fn();
    const newCb = vi.fn();
    ap.onEnded(oldCb);
    ap.onEnded(newCb);
    await ap.play('a', 'data:audio/mp3;base64,a');
    FakeAudio.instances[0].fireEnded();
    expect(oldCb).not.toHaveBeenCalled();
    expect(newCb).toHaveBeenCalledOnce();
  });

  test('stop() does NOT fire onEnded (only natural end does)', async () => {
    const ap = new AudioPlayer();
    const cb = vi.fn();
    ap.onEnded(cb);
    await ap.play('a', 'data:audio/mp3;base64,a');
    ap.stop();
    expect(cb).not.toHaveBeenCalled();
  });
});


// ── volume / mute / playback rate ─────────────────────────────────


describe('AudioPlayer volume controls', () => {
  test('setVolume clamps to [0, 1]', async () => {
    const ap = new AudioPlayer();
    await ap.play('a', 'data:audio/mp3;base64,a');
    ap.setVolume(2);
    expect(FakeAudio.instances[0].volume).toBe(1);
    ap.setVolume(-0.5);
    expect(FakeAudio.instances[0].volume).toBe(0);
  });

  test('setMuted=true zeroes volume; false restores configured volume', async () => {
    const ap = new AudioPlayer();
    ap.setVolume(0.6);
    await ap.play('a', 'data:audio/mp3;base64,a');
    ap.setMuted(true);
    expect(FakeAudio.instances[0].volume).toBe(0);
    ap.setMuted(false);
    expect(FakeAudio.instances[0].volume).toBe(0.6);
  });

  test('setPlaybackRate clamps to [0.5, 2]', async () => {
    const ap = new AudioPlayer();
    await ap.play('a', 'data:audio/mp3;base64,a');
    ap.setPlaybackRate(5);
    expect(FakeAudio.instances[0].playbackRate).toBe(2);
    ap.setPlaybackRate(0.1);
    expect(FakeAudio.instances[0].playbackRate).toBe(0.5);
  });
});


// ── helpers ───────────────────────────────────────────────────────


describe('helpers', () => {
  test('dataUrlForBase64Mp3 wraps with the right MIME', () => {
    expect(dataUrlForBase64Mp3('AAA=')).toBe('data:audio/mp3;base64,AAA=');
  });

  test('createAudioPlayer returns a fresh AudioPlayer instance', () => {
    const a = createAudioPlayer();
    const b = createAudioPlayer();
    expect(a).toBeInstanceOf(AudioPlayer);
    expect(a).not.toBe(b);
  });
});
