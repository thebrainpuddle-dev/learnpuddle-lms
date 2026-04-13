// hooks/usePlaybackEngine.ts — React hook for MAIC playback engine lifecycle
//
// Manages scene-by-scene playback: auto-advances to the next scene when
// the current scene's actions complete, plays an intro pause between scenes,
// and supports full-classroom autoplay.

import { useRef, useEffect, useCallback, useState } from 'react';
import { MAICPlaybackEngine, type PlaybackState } from '../lib/maicPlaybackEngine';
import { MAICActionEngine } from '../lib/maicActionEngine';
import { useMAICStageStore } from '../stores/maicStageStore';
import { useMAICSettingsStore } from '../stores/maicSettingsStore';
import { useAuthStore } from '../stores/authStore';
import type { MAICAction } from '../types/maic-actions';
import type { MAICScene } from '../types/maic-scenes';

const TTS_ENDPOINT = '/api/v1/teacher/maic/generate/tts/';
const SCENE_TRANSITION_DELAY_MS = 1200;

export function usePlaybackEngine() {
  const [playbackState, setPlaybackState] = useState<PlaybackState>('idle');
  const [currentActionIndex, setCurrentActionIndex] = useState(0);
  const [actionCount, setActionCount] = useState(0);
  const [isClassPlaying, setIsClassPlaying] = useState(false);

  const engineRef = useRef<MAICPlaybackEngine | null>(null);
  const actionEngineRef = useRef<MAICActionEngine | null>(null);
  const autoAdvanceRef = useRef(false);
  const classStoppedRef = useRef(false);

  const accessToken = useAuthStore((s) => s.accessToken);
  const setEngineMode = useMAICStageStore((s) => s.setEngineMode);
  const autoPlay = useMAICSettingsStore((s) => s.autoPlay);

  // Initialize engines when token is available
  useEffect(() => {
    if (!accessToken) return;

    const actionEngine = new MAICActionEngine({
      ttsEndpoint: TTS_ENDPOINT,
      token: accessToken,
      onSpeechStart: (agentId: string, text: string) => {
        useMAICStageStore.getState().setSpeakingAgent(agentId);
        useMAICStageStore.getState().setSpeechText(text);
      },
      onSpeechEnd: () => {
        useMAICStageStore.getState().setSpeakingAgent(null);
        useMAICStageStore.getState().setSpeechText(null);
      },
      onDiscussionTrigger: (sessionType: string) => {
        useMAICStageStore
          .getState()
          .setDiscussionMode(sessionType as 'qa' | 'roundtable' | 'classroom');
      },
    });

    const playbackEngine = new MAICPlaybackEngine(actionEngine, {
      onStateChange: (state: PlaybackState) => {
        setPlaybackState(state);
        if (state === 'idle') {
          setEngineMode('idle');
        } else if (state === 'playing') {
          setEngineMode('playing');
        } else if (state === 'paused') {
          setEngineMode('paused');
        }
      },
      onActionStart: (index: number, _action: MAICAction) => {
        setCurrentActionIndex(index);
      },
      onSceneComplete: () => {
        setCurrentActionIndex(0);

        // Auto-advance to next scene if autoplay is active
        if (autoAdvanceRef.current && !classStoppedRef.current) {
          const store = useMAICStageStore.getState();
          const { currentSceneIndex, scenes } = store;
          if (currentSceneIndex < scenes.length - 1) {
            // Brief pause between scenes, then advance
            setTimeout(() => {
              if (classStoppedRef.current) return;
              store.goToScene(currentSceneIndex + 1);
              // The scene change will trigger loadScene via the Stage useEffect,
              // and then we auto-play it
              setTimeout(() => {
                if (classStoppedRef.current) return;
                engineRef.current?.play();
              }, 300);
            }, SCENE_TRANSITION_DELAY_MS);
          } else {
            // All scenes complete
            autoAdvanceRef.current = false;
            setIsClassPlaying(false);
            useMAICStageStore.getState().setPlaying(false);
          }
        }
      },
    });

    actionEngineRef.current = actionEngine;
    engineRef.current = playbackEngine;

    return () => {
      playbackEngine.dispose();
      actionEngine.dispose();
      engineRef.current = null;
      actionEngineRef.current = null;
    };
  }, [accessToken, setEngineMode]);

  // ─── Controls ───────────────────────────────────────────────────────

  const play = useCallback(() => {
    engineRef.current?.play();
  }, []);

  const pause = useCallback(() => {
    engineRef.current?.pause();
  }, []);

  const resume = useCallback(() => {
    engineRef.current?.resume();
  }, []);

  const stop = useCallback(() => {
    engineRef.current?.stop();
  }, []);

  const seekTo = useCallback((index: number) => {
    engineRef.current?.seekTo(index);
    setCurrentActionIndex(index);
  }, []);

  const loadScene = useCallback((scene: MAICScene) => {
    engineRef.current?.loadScene(scene);
    setActionCount(scene.actions?.length ?? 0);
    setCurrentActionIndex(0);
    setPlaybackState('idle');
  }, []);

  // ─── Full-Classroom Playback ──────────────────────────────────────

  /** Start playing from scene 0 through all scenes sequentially */
  const startClass = useCallback(() => {
    const store = useMAICStageStore.getState();
    if (store.scenes.length === 0) return;

    classStoppedRef.current = false;
    autoAdvanceRef.current = true;
    setIsClassPlaying(true);
    store.setPlaying(true);

    // Go to scene 0 and start
    store.goToScene(0);
    setTimeout(() => {
      engineRef.current?.play();
    }, 300);
  }, []);

  /** Start playing from the current scene and auto-advance through remaining */
  const playFromCurrent = useCallback(() => {
    classStoppedRef.current = false;
    autoAdvanceRef.current = true;
    setIsClassPlaying(true);
    useMAICStageStore.getState().setPlaying(true);
    engineRef.current?.play();
  }, []);

  /** Stop full-classroom playback */
  const stopClass = useCallback(() => {
    classStoppedRef.current = true;
    autoAdvanceRef.current = false;
    setIsClassPlaying(false);
    useMAICStageStore.getState().setPlaying(false);
    engineRef.current?.stop();
  }, []);

  return {
    playbackState,
    currentActionIndex,
    actionCount,
    isClassPlaying,
    play,
    pause,
    resume,
    stop,
    seekTo,
    loadScene,
    startClass,
    playFromCurrent,
    stopClass,
  };
}
