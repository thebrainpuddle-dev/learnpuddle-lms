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

// Brief beat between scenes. Was 1200 ms — felt like a dead pause between
// speakers. Dropped to 400 ms: enough for the slide transition animation
// (~300 ms fade/slide) to breathe without producing an audible silence.
// Speech prefetch (scene-wide on loadScene) + audio-unlock keep the next
// scene's first audio starting cleanly right at the end of the beat.
const SCENE_TRANSITION_DELAY_MS = 400;

export function usePlaybackEngine(role: MAICRole = 'teacher') {
  const [playbackState, setPlaybackState] = useState<PlaybackState>('idle');
  const [currentActionIndex, setCurrentActionIndex] = useState(0);
  const [actionCount, setActionCount] = useState(0);
  const [isClassPlaying, setIsClassPlaying] = useState(false);
  // SPRINT-2-BATCH-9-F10 — terminal "classroom complete" flag. Flips true
  // ONLY when the engine fires `onSceneComplete` for the LAST scene while
  // autoplay was driving the chain (i.e. the user reached the natural end
  // of the classroom, not a manual stop). Cleared by every entry point
  // that re-starts or rewinds playback so the e2e/screen-reader testid
  // disappears before it can stick across runs.
  const [classroomComplete, setClassroomComplete] = useState(false);

  const engineRef = useRef<MAICPlaybackEngine | null>(null);
  const actionEngineRef = useRef<MAICActionEngine | null>(null);
  const autoAdvanceRef = useRef(false);
  const classStoppedRef = useRef(false);
  const sceneAdvanceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const startDelayTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Engine-driven slide change flag: set by the action engine's
  // onEngineDrivenTransition callback (and by `seekToSlide` below) so
  // Stage.tsx's auto-pause effect can distinguish "engine is seeking"
  // from "user is clicking". The useEffect consumes + clears the flag.
  // Hoisted above the main init useEffect so the closure captures it.
  const engineDrivenSlideChangeRef = useRef(false);

  const accessToken = useAuthStore((s) => s.accessToken);
  const hasAccessToken = Boolean(accessToken);
  const setEngineMode = useMAICStageStore((s) => s.setEngineMode);
  const autoPlay = useMAICSettingsStore((s) => s.autoPlay);
  // Offline-audio-durability re-wire (2026-04-26): thread the classroom id
  // into the action engine so prefetched TTS buffers persist to IDB and the
  // live-TTS fetch fallback can read them back. Subscribed to the store so
  // the engine is rebuilt when navigating between classrooms.
  const classroomId = useMAICStageStore((s) => s.classroomId);

  const clearQueuedPlaybackTimers = useCallback(() => {
    if (sceneAdvanceTimerRef.current) {
      clearTimeout(sceneAdvanceTimerRef.current);
      sceneAdvanceTimerRef.current = null;
    }
    if (startDelayTimerRef.current) {
      clearTimeout(startDelayTimerRef.current);
      startDelayTimerRef.current = null;
    }
  }, []);

  // Initialize engines when token is available
  useEffect(() => {
    const token = useAuthStore.getState().accessToken;
    if (!hasAccessToken || !token) return;

    const ttsEndpoint = maicTtsUrl(role);
    const actionEngine = new MAICActionEngine({
      ttsEndpoint,
      token,
      classroomId: classroomId ?? undefined,
      onSpeechStart: (agentId: string, text: string) => {
        const s = useMAICStageStore.getState();
        s.setSpeakingAgent(agentId);
        s.setSpeechText(text);
        s.setIsSpeaking(true);
      },
      onSpeechEnd: () => {
        // T0.2 — flip off the "actively speaking" flag (voice wave stops)
        // but leave `speakingAgent` + `speechText` intact so the bubble
        // holds the last spoken line until the next onSpeechStart
        // overwrites them. Matches OpenMAIC: "last sentence stays on
        // screen between speakers". Scene change / stop() resets below.
        useMAICStageStore.getState().setIsSpeaking(false);
      },
      // NOTE: we no longer wire `onDiscussionTrigger` to `setDiscussionMode`.
      // That was the "discussion suddenly opens" seam — it flipped the
      // panel on the same tick the engine hit the discussion action,
      // before the user got a breath. The playback engine's separate
      // `onDiscussionPending` path now owns the transition through the
      // breath + Join/Skip gate in DiscussionGateCard.
      onTtsUnavailable: () => {
        // Fire a single info toast per engine lifetime. We can't call
        // `useToast()` here (not a React context), so the host surfaces
        // it via a window event the Stage listens for.
        if (typeof window !== 'undefined') {
          window.dispatchEvent(new Event('maic:tts-unavailable'));
        }
      },
      // Flip the engine-driven flag BEFORE the slide index changes so
      // Stage.tsx's auto-pause effect treats this as playback-driven
      // (not a user click) and doesn't spuriously pause the engine.
      onEngineDrivenTransition: () => {
        engineDrivenSlideChangeRef.current = true;
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
        // Engine soft-paused itself and emitted a pending discussion.
        // We park the metadata in `discussionPending` rather than flipping
        // `discussionMode` directly so `DiscussionGateCard` can render a
        // 3 s breath + Join/Skip countdown first. If the user clicks Join,
        // `DiscussionGateCard` promotes pending → discussionMode, opening
        // RoundtablePanel. If they Skip, it calls resumeAfterDiscussion()
        // which un-pauses the engine to the next action.
        useMAICStageStore.getState().setDiscussionPending({
          topic,
          agentIds,
          sessionType: sessionType as 'qa' | 'roundtable' | 'classroom',
        });
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
            if (sceneAdvanceTimerRef.current) {
              clearTimeout(sceneAdvanceTimerRef.current);
            }
            sceneAdvanceTimerRef.current = setTimeout(() => {
              sceneAdvanceTimerRef.current = null;
              if (classStoppedRef.current || !autoAdvanceRef.current) return;
              const latest = useMAICStageStore.getState();
              if (latest.currentSceneIndex !== currentSceneIndex) return;
              latest.goToScene(currentSceneIndex + 1);
            }, SCENE_TRANSITION_DELAY_MS);
          } else {
            // All scenes complete
            autoAdvanceRef.current = false;
            setIsClassPlaying(false);
            useMAICStageStore.getState().setPlaying(false);
            // SPRINT-2-BATCH-9-F10 — engine reached the terminal state:
            // we just finished the LAST scene's actions and there is no
            // next scene to advance into. This is the e2e/SR-stable
            // "classroom complete" signal.
            setClassroomComplete(true);
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
      clearQueuedPlaybackTimers();
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
  }, [hasAccessToken, setEngineMode, role, classroomId, clearQueuedPlaybackTimers]);

  // ─── Controls ───────────────────────────────────────────────────────

  const play = useCallback(() => {
    clearQueuedPlaybackTimers();
    if (!engineRef.current?.hasPlayableActions()) {
      setIsClassPlaying(false);
      useMAICStageStore.getState().setPlaying(false);
      setPlaybackState('idle');
      return;
    }
    useMAICStageStore.getState().setPlaying(true);
    engineRef.current?.play();
  }, [clearQueuedPlaybackTimers]);

  const pause = useCallback(() => {
    clearQueuedPlaybackTimers();
    useMAICStageStore.getState().setPlaying(false);
    engineRef.current?.pause();
  }, [clearQueuedPlaybackTimers]);

  const resume = useCallback(() => {
    clearQueuedPlaybackTimers();
    useMAICStageStore.getState().setPlaying(true);
    engineRef.current?.resume();
  }, [clearQueuedPlaybackTimers]);

  const stop = useCallback(() => {
    clearQueuedPlaybackTimers();
    autoAdvanceRef.current = false;
    classStoppedRef.current = true;
    setIsClassPlaying(false);
    useMAICStageStore.getState().setPlaying(false);
    engineRef.current?.stop();
  }, [clearQueuedPlaybackTimers]);

  const seekTo = useCallback((index: number) => {
    engineRef.current?.seekTo(index);
    setCurrentActionIndex(index);
  }, []);

  // CG-P1-7 (2026-04-27): the auto-play `seekToSlide` hook export was
  // never wired to the UI (Stage.tsx comment confirmed it). The engine
  // method `MAICPlaybackEngine.seekToSlide` stays for the test suite,
  // but the hook-level callback + return entry are removed. `seekToSlidePaused`
  // below is the UI-facing seek (used by Stage on manual slide click).

  /**
   * CG-P0-9: cursor-only seek to the action that corresponds to a given
   * slide. Doesn't auto-play. Used by Stage when the user manually clicks
   * a slide thumbnail or swipes — so the SUBSEQUENT Play press starts the
   * engine at the speech that matches the visible slide instead of
   * restarting from the scene's intro speech.
   *
   * `slideIndex` is SCENE-RELATIVE (matches `TransitionAction.slideIndex`,
   * which is documented as "Target slide index within the current scene").
   * Caller is responsible for the absolute → relative conversion via
   * `sceneSlideBounds`.
   */
  const seekToSlidePaused = useCallback((slideIndex: number) => {
    if (!engineRef.current) return;
    engineRef.current.seekToSlidePaused(slideIndex);
  }, []);

  /**
   * Scene-chip click handler. Synchronizes the engine atomically with the
   * scene change so a subsequent Play button press cannot race a
   * partially-loaded scene:
   *
   *   1. Flip engineDrivenSlideChangeRef so Stage's auto-pause effect
   *      doesn't spuriously pause us on the imminent slide-index change.
   *   2. Stop the engine synchronously — aborts any in-flight audio or
   *      timers. This must happen BEFORE the store update so stale audio
   *      from the prior scene cannot leak into the new scene.
   *   3. Update the store, which fires Stage's useEffect to loadScene
   *      the new scene (fresh action list, currentActionIndex = 0).
   *
   * The engine is left in 'idle' state — the user's Play press then
   * plays from action 0 of the freshly loaded scene, deterministically.
   */
  const seekToScene = useCallback((sceneIndex: number) => {
    const shouldContinuePlayback = autoAdvanceRef.current && !classStoppedRef.current;
    clearQueuedPlaybackTimers();
    autoAdvanceRef.current = shouldContinuePlayback;
    classStoppedRef.current = !shouldContinuePlayback;
    setIsClassPlaying(shouldContinuePlayback);
    useMAICStageStore.getState().setPlaying(shouldContinuePlayback);
    engineDrivenSlideChangeRef.current = true;
    engineRef.current?.stop();
    useMAICStageStore.getState().goToScene(sceneIndex);
  }, [clearQueuedPlaybackTimers]);

  const resumeAfterDiscussion = useCallback(() => {
    engineRef.current?.resumeAfterDiscussion();
  }, []);

  // Porting P4.1 — student interrupt path exposed to chat/voice senders.
  const handleUserInterrupt = useCallback((text: string) => {
    engineRef.current?.handleUserInterrupt(text);
  }, []);
  const resumeAfterInterrupt = useCallback(() => {
    engineRef.current?.resumeAfterInterrupt();
  }, []);

  // V.1-fix — UI-initiated discussion entry (ProactiveCard, manual
  // Roundtable button). Pauses engine + saves checkpoint so
  // resumeAfterDiscussion() replays cleanly when the panel closes.
  const enterDiscussionFromUI = useCallback(() => {
    engineRef.current?.enterDiscussionFromUI();
  }, []);

  const loadScene = useCallback((scene: MAICScene) => {
    // loadScene() calls stop() internally, which bumps the action engine's
    // generationToken and tears down any in-flight audio synchronously.
    // That makes the previous 150 ms setTimeout unnecessary — the token
    // guarantees a clean start with no stale callbacks leaking through.
    engineRef.current?.loadScene(scene);
    setActionCount(engineRef.current?.getActionCount() ?? scene.actions?.length ?? 0);
    setCurrentActionIndex(0);
    setPlaybackState('idle');
    // SPRINT-2-BATCH-9-F10 — any new scene load (manual nav, scene-chip
    // click, resume after the user backs up) clears the terminal flag.
    setClassroomComplete(false);

    if (autoAdvanceRef.current && !classStoppedRef.current) {
      engineRef.current?.play();
    }
  }, []);

  // ─── Full-Classroom Playback ──────────────────────────────────────

  /** Start playing from scene 0 through all scenes sequentially */
  const startClass = useCallback(() => {
    const store = useMAICStageStore.getState();
    if (store.scenes.length === 0) return;

    clearQueuedPlaybackTimers();
    classStoppedRef.current = false;
    autoAdvanceRef.current = true;
    setIsClassPlaying(true);
    store.setPlaying(true);
    // SPRINT-2-BATCH-9-F10 — re-starting the class from the top clears
    // the terminal flag so the testid disappears before the new run.
    setClassroomComplete(false);

    // Audio pipeline unlock: startClass runs inside the click handler that
    // the user pressed to begin the class, so a silent-buffer play() here
    // satisfies the browser's user-gesture requirement. Without this,
    // subsequent auto-advanced audio.play() calls get rejected with
    // NotAllowedError and the entire class plays silently.
    actionEngineRef.current?.unlockAudio();

    // Go to scene 0 and start
    store.goToScene(0);
    startDelayTimerRef.current = setTimeout(() => {
      startDelayTimerRef.current = null;
      if (classStoppedRef.current || !autoAdvanceRef.current) return;
      engineRef.current?.play();
    }, 300);
  }, [clearQueuedPlaybackTimers]);

  /** Start playing from the current scene and auto-advance through remaining */
  const playFromCurrent = useCallback(() => {
    clearQueuedPlaybackTimers();
    if (!engineRef.current?.hasPlayableActions()) {
      autoAdvanceRef.current = false;
      classStoppedRef.current = true;
      setIsClassPlaying(false);
      useMAICStageStore.getState().setPlaying(false);
      setPlaybackState('idle');
      return;
    }
    classStoppedRef.current = false;
    autoAdvanceRef.current = true;
    setIsClassPlaying(true);
    useMAICStageStore.getState().setPlaying(true);
    // SPRINT-2-BATCH-9-F10 — resuming from a non-terminal scene clears
    // the flag (the user has navigated back into the body of the class).
    setClassroomComplete(false);
    // User gesture: unlock audio on every play press so paused-and-resumed
    // classrooms don't revert to blocked state after a long idle.
    actionEngineRef.current?.unlockAudio();
    engineRef.current?.play();
  }, [clearQueuedPlaybackTimers]);

  // CG-P1-7: `stopClass` was exported but no UI caller. `pause()` covers
  // user-initiated stops; auto-advance ends naturally via onSceneComplete
  // when the last scene finishes. Removed.

  /**
   * Consume-once flag indicating the most recent `currentSlideIndex` change
   * came from an engine-initiated path (seekToSlide or executeTransition).
   * Stage's auto-pause useEffect calls this to skip the pause when the
   * engine is driving the slide change. The read is destructive — the
   * flag is reset to false whenever inspected.
   */
  const consumeEngineDrivenSlideChange = useCallback(() => {
    const wasEngineDriven = engineDrivenSlideChangeRef.current;
    engineDrivenSlideChangeRef.current = false;
    return wasEngineDriven;
  }, []);

  return {
    playbackState,
    currentActionIndex,
    actionCount,
    isClassPlaying,
    classroomComplete,
    play,
    pause,
    resume,
    stop,
    seekTo,
    // CG-P1-7: `seekToSlide` and `stopClass` removed — never wired to UI.
    // Engine-level `MAICPlaybackEngine.seekToSlide` stays for tests.
    seekToSlidePaused,
    seekToScene,
    loadScene,
    resumeAfterDiscussion,
    enterDiscussionFromUI,
    handleUserInterrupt,
    resumeAfterInterrupt,
    startClass,
    playFromCurrent,
    consumeEngineDrivenSlideChange,
  };
}
