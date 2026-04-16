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
import { maicTtsUrl, type MAICRole } from '../lib/maic/endpoints';

const SCENE_TRANSITION_DELAY_MS = 1200;

export function usePlaybackEngine(role: MAICRole = 'teacher') {
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

    const ttsEndpoint = maicTtsUrl(role);
    const actionEngine = new MAICActionEngine({
      ttsEndpoint,
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
      onDiscussionPending: (topic: string, agentIds: string[], sessionType: string) => {
        // Discussion triggered — the engine has soft-paused itself.
        // The RoundtablePanel will show and call resumeAfterDiscussion() when done.
        useMAICStageStore
          .getState()
          .setDiscussionMode(sessionType as 'qa' | 'roundtable' | 'classroom');
      },
      onSceneComplete: () => {
        setCurrentActionIndex(0);

        // Auto-advance to next scene if autoplay is active
        if (autoAdvanceRef.current && !classStoppedRef.current) {
          const store = useMAICStageStore.getState();
          const { currentSceneIndex, scenes } = store;
          if (currentSceneIndex < scenes.length - 1) {
            // Brief pause between scenes, then advance.
            // The scene change triggers loadScene via Stage useEffect,
            // which auto-plays because autoAdvanceRef is true.
            setTimeout(() => {
              if (classStoppedRef.current) return;
              store.goToScene(currentSceneIndex + 1);
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

    // Expose the engines on `window.__maicEngine` under test/dev so e2e
    // Playwright probes can inspect `audioElement`, `generationToken`, etc.
    // In production builds (MODE === 'production' && !DEV) this is a no-op.
    if (
      typeof window !== 'undefined' &&
      (import.meta.env.MODE === 'test' || import.meta.env.DEV)
    ) {
      (window as any).__maicEngine = {
        actionEngine,
        playbackEngine,
      };
    }

    return () => {
      playbackEngine.dispose();
      actionEngine.dispose();
      engineRef.current = null;
      actionEngineRef.current = null;
      if (
        typeof window !== 'undefined' &&
        (import.meta.env.MODE === 'test' || import.meta.env.DEV)
      ) {
        delete (window as any).__maicEngine;
      }
    };
  }, [accessToken, setEngineMode, role]);

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

  /**
   * Seek to the transition action for a given slide index (within the current
   * scene) and start playing from there. Triggered by slide-thumbnail clicks
   * mid-playback. Uses `generationToken` internally to guarantee the previous
   * slide's audio cannot wake up and corrupt the new slide's state.
   */
  const seekToSlide = useCallback((slideIndex: number) => {
    engineRef.current?.seekToSlide(slideIndex);
  }, []);

  const resumeAfterDiscussion = useCallback(() => {
    engineRef.current?.resumeAfterDiscussion();
  }, []);

  const loadScene = useCallback((scene: MAICScene) => {
    // loadScene() calls stop() internally, which bumps the action engine's
    // generationToken and tears down any in-flight audio synchronously.
    // That makes the previous 150 ms setTimeout unnecessary — the token
    // guarantees a clean start with no stale callbacks leaking through.
    engineRef.current?.loadScene(scene);
    setActionCount(scene.actions?.length ?? 0);
    setCurrentActionIndex(0);
    setPlaybackState('idle');

    if (autoAdvanceRef.current && !classStoppedRef.current) {
      engineRef.current?.play();
    }
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
    seekToSlide,
    loadScene,
    resumeAfterDiscussion,
    startClass,
    playFromCurrent,
    stopClass,
  };
}
