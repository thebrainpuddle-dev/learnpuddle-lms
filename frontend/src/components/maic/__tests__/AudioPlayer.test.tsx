import React from 'react';
import { render, waitFor } from '@testing-library/react';
import { afterAll, afterEach, beforeEach, describe, expect, test, vi } from 'vitest';

import { AudioPlayer } from '../AudioPlayer';
import { useMAICStageStore } from '../../../stores/maicStageStore';

describe('AudioPlayer', () => {
  const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

  beforeEach(() => {
    useMAICStageStore.getState().reset();
    warnSpy.mockClear();
  });

  afterEach(() => {
    useMAICStageStore.getState().reset();
  });

  afterAll(() => {
    warnSpy.mockRestore();
  });

  test('does not hand the authenticated TTS POST endpoint to an audio element', async () => {
    const onUnavailable = vi.fn();
    window.addEventListener('maic:tts-unavailable', onUnavailable);
    useMAICStageStore.getState().setPlaying(true);

    const { container, unmount } = render(
      <AudioPlayer audioUrl="/api/v1/teacher/maic/generate/tts/" />,
    );

    await waitFor(() => {
      expect(onUnavailable).toHaveBeenCalledTimes(1);
      expect(useMAICStageStore.getState().isPlaying).toBe(false);
    });

    const audio = container.querySelector('audio');
    expect(audio?.getAttribute('src')).toBeNull();
    expect(warnSpy).toHaveBeenCalledWith(
      '[MAIC] ignoring invalid slide audioUrl',
      '/api/v1/teacher/maic/generate/tts/',
    );

    window.removeEventListener('maic:tts-unavailable', onUnavailable);
    unmount();
  });
});
