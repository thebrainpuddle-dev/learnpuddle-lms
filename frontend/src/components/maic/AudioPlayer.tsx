// src/components/maic/AudioPlayer.tsx
//
// TTS audio playback component synced with the stage store. Plays the
// current slide's audioUrl, respects volume/speed settings, and
// auto-advances to the next slide when audio ends if autoPlay is enabled.

import React, { useRef, useEffect, useCallback } from 'react';
import { useMAICStageStore } from '../../stores/maicStageStore';
import { useMAICSettingsStore } from '../../stores/maicSettingsStore';
import type { MAICEngineMode } from '../../types/maic-scenes';

interface AudioPlayerProps {
  audioUrl?: string;
}

export const AudioPlayer = React.memo<AudioPlayerProps>(function AudioPlayer({ audioUrl }) {
  const audioRef = useRef<HTMLAudioElement>(null);

  const isPlaying = useMAICStageStore((s) => s.isPlaying);
  const setPlaying = useMAICStageStore((s) => s.setPlaying);
  const nextSlide = useMAICStageStore((s) => s.nextSlide);
  const currentSlideIndex = useMAICStageStore((s) => s.currentSlideIndex);
  const slides = useMAICStageStore((s) => s.slides);

  const engineMode = useMAICStageStore((s) => s.engineMode);
  const audioVolume = useMAICSettingsStore((s) => s.audioVolume);
  const playbackSpeed = useMAICSettingsStore((s) => s.playbackSpeed);
  const autoPlay = useMAICSettingsStore((s) => s.autoPlay);

  // Sync volume
  useEffect(() => {
    if (audioRef.current) {
      audioRef.current.volume = audioVolume;
    }
  }, [audioVolume]);

  // Sync playback speed
  useEffect(() => {
    if (audioRef.current) {
      audioRef.current.playbackRate = playbackSpeed;
    }
  }, [playbackSpeed]);

  // Play / pause based on isPlaying state
  useEffect(() => {
    const audio = audioRef.current;
    if (!audio || !audioUrl) return;

    if (isPlaying) {
      audio.play().catch(() => {
        // Autoplay may be blocked by browser policy
        setPlaying(false);
      });
    } else {
      audio.pause();
    }
  }, [isPlaying, audioUrl, setPlaying]);

  // Reset audio when URL changes (new slide)
  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    if (audioUrl) {
      audio.src = audioUrl;
      audio.load();
      if (isPlaying) {
        audio.play().catch(() => setPlaying(false));
      }
    } else {
      audio.removeAttribute('src');
      audio.load();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [audioUrl]);

  // Handle audio ended — only auto-advance when the playback engine is NOT
  // managing audio (engine drives its own scene progression via onSceneComplete).
  const handleEnded = useCallback(() => {
    // When the engine is actively playing scenes, it handles progression.
    if (engineMode === 'playing' || engineMode === 'paused') {
      setPlaying(false);
      return;
    }

    const isLastSlide = currentSlideIndex >= slides.length - 1;

    if (autoPlay && !isLastSlide) {
      nextSlide();
      // isPlaying stays true; the new slide's audio will begin via useEffect
    } else {
      setPlaying(false);
    }
  }, [autoPlay, currentSlideIndex, slides.length, nextSlide, setPlaying, engineMode]);

  // This is a headless audio element; no visible UI. Playback controls are
  // in StageToolbar and SlideNavigator. Use preload="none" to avoid Range
  // request errors on blob URLs; playback is managed programmatically.
  return (
    <audio
      ref={audioRef}
      onEnded={handleEnded}
      preload="none"
      aria-hidden="true"
    />
  );
});
