// src/components/maic/Stage.tsx
//
// Main container component for the MAIC AI Classroom player. Composes
// SceneRenderer, Whiteboard, ChatPanel, SlideNavigator, StageToolbar,
// AgentAvatar, AudioPlayer, SpotlightOverlay,
// RoundtablePanel, ExportMenu, SceneSidebar, and keyboard shortcuts
// into a unified interactive stage.

import React, { useState, useMemo, useCallback, useEffect, useRef } from 'react';
import { AnimatePresence } from 'motion/react';
import { useMAICStageStore } from '../../stores/maicStageStore';
import { useMAICSettingsStore } from '../../stores/maicSettingsStore';
import { initKeyboardListeners } from '../../stores/maicKeyboardStore';
import { usePlaybackEngine } from '../../hooks/usePlaybackEngine';
import { useKeyboardShortcuts } from '../../hooks/useKeyboardShortcuts';
import { useDocumentPiP } from '../../hooks/useDocumentPiP';
import type { MAICPlayerRole } from '../../types/maic';
import type { MAICSlideContent } from '../../types/maic-scenes';
import { SceneRenderer } from './SceneRenderer';
import { SlideRenderer } from './SlideRenderer';
import { Whiteboard } from './Whiteboard';
import { ChatPanel } from './ChatPanel';
import { SlideNavigator } from './SlideNavigator';
import { StageToolbar } from './StageToolbar';
import { PresentationSpeechOverlay } from './PresentationSpeechOverlay';
import { AudioPlayer } from './AudioPlayer';
import { SpotlightOverlay } from './SpotlightOverlay';
import { RoundtablePanel } from './RoundtablePanel';
import { ExportMenu } from './ExportMenu';
import { SceneSidebar } from './SceneSidebar';
import { ProactiveCardManager } from './ProactiveCardManager';
import { RoundtableStrip } from './RoundtableStrip';
import { KeyboardHelpOverlay } from './KeyboardHelpOverlay';
import { DiscussionGateCard } from './DiscussionGateCard';
import { EndSessionFlash, useEndSessionFlash } from './EndSessionFlash';
import { ConfirmDialog } from '../common';
import { useSprintFlag, SPRINT1_FLAGS } from '../../lib/sprintFlags';
import { readPosition, savePosition, clearPosition } from '../../lib/playbackPersistence';
import { useToast } from '../common/Toast';
import { HighlightOverlay } from './HighlightOverlay';
import { LaserPointer } from './LaserPointer';
import { cn } from '../../lib/utils';

interface StageProps {
  role: MAICPlayerRole;
  /**
   * CG-P0-3: forwarded from the classroom detail response.  When true the
   * Celery image-fill task is still running; image elements with empty src
   * show a "fetching image…" skeleton.
   */
  imagesPending?: boolean;
}

export const Stage: React.FC<StageProps> = ({ role, imagesPending }) => {
  const slides = useMAICStageStore((s) => s.slides);
  const currentSlideIndex = useMAICStageStore((s) => s.currentSlideIndex);
  const agents = useMAICStageStore((s) => s.agents);
  const speakingAgentId = useMAICStageStore((s) => s.speakingAgentId);
  const isFullscreen = useMAICStageStore((s) => s.isFullscreen);
  const setFullscreen = useMAICStageStore((s) => s.setFullscreen);
  const classroomId = useMAICStageStore((s) => s.classroomId);
  const scenes = useMAICStageStore((s) => s.scenes);
  const currentSceneIndex = useMAICStageStore((s) => s.currentSceneIndex);
  const speechText = useMAICStageStore((s) => s.speechText);
  const discussionMode = useMAICStageStore((s) => s.discussionMode);
  const setDiscussionMode = useMAICStageStore((s) => s.setDiscussionMode);
  const discussionPending = useMAICStageStore((s) => s.discussionPending);
  const setDiscussionPending = useMAICStageStore((s) => s.setDiscussionPending);
  const nextScene = useMAICStageStore((s) => s.nextScene);
  const goToScene = useMAICStageStore((s) => s.goToScene);

  const goToSlide = useMAICStageStore((s) => s.goToSlide);
  // CG-P0-9: read sceneSlideBounds for converting absolute → scene-relative
  // slide index when seeking the engine cursor on manual navigation.
  const sceneSlideBounds = useMAICStageStore((s) => s.sceneSlideBounds);

  const showChatPanel = useMAICSettingsStore((s) => s.showChatPanel);
  const setShowChatPanel = useMAICSettingsStore((s) => s.setShowChatPanel);
  const showWhiteboard = useMAICSettingsStore((s) => s.showWhiteboard);
  const audioVolume = useMAICSettingsStore((s) => s.audioVolume);
  const setAudioVolume = useMAICSettingsStore((s) => s.setAudioVolume);

  const spotlightElementId = useMAICStageStore((s) => s.spotlightElementId);
  const setSpotlightElementId = useMAICStageStore((s) => s.setSpotlightElementId);
  const laserElementId = useMAICStageStore((s) => s.laserElementId);
  const laserColor = useMAICStageStore((s) => s.laserColor);

  const [spotlightActive, setSpotlightActive] = useState(false);
  const [showSceneSidebar, setShowSceneSidebar] = useState(false);
  const [showKeyboardHelp, setShowKeyboardHelp] = useState(false);
  // T6 — pending scene switch that's waiting on a "discussion is active"
  // confirm. We remember the target index so Confirm can fire the
  // actual seek after cleanly closing the discussion.
  const [pendingSceneSwitch, setPendingSceneSwitch] = useState<number | null>(null);

  const roundtableStripEnabled = useSprintFlag(SPRINT1_FLAGS.roundtableStrip);

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return;
    const media = window.matchMedia('(max-width: 767px)');
    const closeDrawerOnMobile = () => {
      if (media.matches) setShowChatPanel(false);
    };
    closeDrawerOnMobile();
    media.addEventListener('change', closeDrawerOnMobile);
    return () => media.removeEventListener('change', closeDrawerOnMobile);
  }, [setShowChatPanel]);

  // Sprint 4 · B.7 — presentation-mode auto-hide controls. When the
  // user enters fullscreen the toolbar + bottom navigator fade out
  // after 3 s of inactivity and reappear on any mouse move, key press,
  // or touch. Outside fullscreen we force them visible.
  //
  // R3 (WAVE-9 deferred) — the timer handle lives in a `useRef` rather
  // than a closure-local `let`. The original `let timer` worked for the
  // common case but had two latent footguns:
  //   1. Under React 18 strict-mode double-invoke each effect pass got
  //      its own closure, so a setTimeout scheduled in pass A could
  //      survive cleanup of pass B if any future edit accidentally
  //      moved the schedule call out of the effect body.
  //   2. The post-cleanup `setControlsVisible(false)` callback could
  //      still fire between an `isFullscreen=false` toggle and
  //      cleanup-completion if a future edit deferred any cleanup work.
  // A ref-tracked handle plus an `unmounted` flag make both cases
  // explicit and unit-testable (see Stage.revealTimer.test.tsx).
  const [controlsVisible, setControlsVisible] = useState(true);
  const revealTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (!isFullscreen) {
      // Always clear any pending hide-timer when leaving fullscreen so
      // the controls don't get yanked invisible a moment after the
      // user exits.
      if (revealTimerRef.current) {
        clearTimeout(revealTimerRef.current);
        revealTimerRef.current = null;
      }
      setControlsVisible(true);
      return;
    }
    let cancelled = false;
    const reveal = () => {
      if (cancelled) return;
      setControlsVisible(true);
      if (revealTimerRef.current) clearTimeout(revealTimerRef.current);
      revealTimerRef.current = setTimeout(() => {
        if (cancelled) return;
        setControlsVisible(false);
        revealTimerRef.current = null;
      }, 3000);
    };
    reveal();
    window.addEventListener('mousemove', reveal);
    window.addEventListener('keydown', reveal);
    window.addEventListener('touchstart', reveal, { passive: true });
    return () => {
      cancelled = true;
      if (revealTimerRef.current) {
        clearTimeout(revealTimerRef.current);
        revealTimerRef.current = null;
      }
      window.removeEventListener('mousemove', reveal);
      window.removeEventListener('keydown', reveal);
      window.removeEventListener('touchstart', reveal);
    };
  }, [isFullscreen]);

  // ─── Sprint 3 · B.9 — Resume playback from last position ───────────
  // On mount (per classroom) check localStorage for a saved scene/slide
  // pair and offer a "Continue from scene N?" chip. The chip stays up
  // until the user clicks Continue (jumps to saved position) or Start
  // from beginning (clears the saved position). Once playback moves,
  // every scene/slide change writes back to localStorage.
  const [resumeTarget, setResumeTarget] = useState<{ sceneIndex: number; slideIndex: number } | null>(null);
  const resumeCheckedRef = useRef<string | null>(null);
  useEffect(() => {
    if (!classroomId) return;
    if (resumeCheckedRef.current === classroomId) return;
    if (scenes.length === 0) return; // wait for scenes to load
    resumeCheckedRef.current = classroomId;
    const saved = readPosition(classroomId);
    if (!saved) return;
    // Only offer resume if it's past the start and still within bounds.
    if (saved.sceneIndex <= 0 && saved.slideIndex <= 0) return;
    if (saved.sceneIndex >= scenes.length) return;
    setResumeTarget({ sceneIndex: saved.sceneIndex, slideIndex: saved.slideIndex });
  }, [classroomId, scenes.length]);
  useEffect(() => {
    if (!classroomId) return;
    if (scenes.length === 0) return;
    // Avoid saving the zero state before the user has moved at all — it
    // would re-write every freshly-opened classroom to "position 0" and
    // suppress future resume prompts from a *prior* session. We only
    // save once the user has moved off (0, 0).
    if (currentSceneIndex === 0 && currentSlideIndex === 0) return;
    savePosition(classroomId, currentSceneIndex, currentSlideIndex);
  }, [classroomId, currentSceneIndex, currentSlideIndex, scenes.length]);
  const acceptResume = useCallback(() => {
    if (resumeTarget) {
      goToScene(resumeTarget.sceneIndex);
      // goToScene snaps to the scene's first slide; nudge to exact slide.
      if (resumeTarget.slideIndex > 0) {
        goToSlide(resumeTarget.slideIndex);
      }
    }
    setResumeTarget(null);
  }, [resumeTarget, goToScene, goToSlide]);
  const dismissResume = useCallback(() => {
    if (classroomId) clearPosition(classroomId);
    setResumeTarget(null);
  }, [classroomId]);

  // ─── Mobile Swipe Navigation ──────────────────────────────────────
  const touchStartRef = useRef<number>(0);
  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    touchStartRef.current = e.touches[0].clientX;
  }, []);
  const handleTouchEnd = useCallback(
    (e: React.TouchEvent) => {
      const diff = touchStartRef.current - e.changedTouches[0].clientX;
      if (Math.abs(diff) > 50) {
        if (diff > 0) goToSlide(currentSlideIndex + 1); // swipe left = next
        else goToSlide(currentSlideIndex - 1); // swipe right = prev
      }
    },
    [goToSlide, currentSlideIndex],
  );

  // Playback engine. `seekToSlide` + `stopClass` are no longer wired to UI
  // (scene-only navigator removed per-slide clicks) but the engine still
  // exposes them for programmatic use.
  const {
    playbackState,
    isClassPlaying,
    classroomComplete,
    pause,
    resume,
    loadScene,
    resumeAfterDiscussion,
    enterDiscussionFromUI,
    handleUserInterrupt,
    resumeAfterInterrupt,
    playFromCurrent,
    seekToScene,
    seekToSlidePaused,
    consumeEngineDrivenSlideChange,
  } = usePlaybackEngine(role);

  // Current scene & slide — memoized so child components and effect deps
  // don't see a new reference every render. Without the memo, each re-render
  // (e.g. from a React-Query poll replacing the scenes array during GENERATING)
  // would hand a fresh object to the scene-load effect below, which calls
  // setState inside loadScene and re-renders → new reference → infinite loop
  // that React catches as "Maximum update depth exceeded".
  const hasScenes = scenes.length > 0;
  const currentScene = useMemo(
    () => scenes[currentSceneIndex] || null,
    [scenes, currentSceneIndex],
  );
  const currentSlide = useMemo(
    () => slides[currentSlideIndex] || null,
    [slides, currentSlideIndex],
  );
  const currentSceneHasLinearPlayback = Boolean(
    currentScene &&
      !['quiz', 'pbl', 'interactive'].includes(currentScene.type) &&
      (currentScene.actions?.length ?? 0) > 0,
  );

  // Load scene actions when scene changes. Key on the stable scene id (not
  // the object reference) so re-fetches that return an equivalent payload
  // don't falsely trip the effect.
  useEffect(() => {
    if (currentScene) {
      loadScene(currentScene);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentScene?.id, loadScene]);

  // Stop current audio when user MANUALLY navigates to a different slide.
  // Skip the auto-pause when the slide change was engine-driven —
  //   a) during autoplay the engine's executeTransition changes the slide
  //      between actions (covered by isClassPlaying),
  //   b) when seekToSlide is called from a thumbnail click the hook sets
  //      a consume-once flag (covered by consumeEngineDrivenSlideChange).
  // Only user-driven changes (prev/next buttons, keyboard shortcuts) should
  // pause the engine.
  //
  // CG-P0-9 (2026-04-27): also seek the engine cursor to the action that
  // matches the visible slide. Previously a manual slide click left the
  // engine at action[0] of the (possibly newly-loaded) scene; pressing
  // Play afterwards would replay the scene's intro speech regardless of
  // which slide was visible — total audio/slide desync. We now convert
  // the absolute `currentSlideIndex` to scene-relative (subtract the
  // scene's startSlide from sceneSlideBounds) and call
  // `seekToSlidePaused`, which the engine resolves via its
  // `resolveSlideSeekTarget` helper to the matching transition action.
  const prevSlideIndexRef = useRef(currentSlideIndex);
  useEffect(() => {
    if (prevSlideIndexRef.current !== currentSlideIndex) {
      const engineDriven = consumeEngineDrivenSlideChange();
      if (!engineDriven) {
        if (!isClassPlaying && playbackState === 'playing') {
          pause();
        }
        // Compute the scene-relative slide index. sceneSlideBounds is the
        // {sceneIdx, startSlide, endSlide} mapping populated by the wizard.
        // Fall back to the absolute index if no bounds yet (legacy 1:1).
        const bound = sceneSlideBounds.find(
          (b) => currentSlideIndex >= b.startSlide && currentSlideIndex <= b.endSlide,
        );
        const relative = bound ? currentSlideIndex - bound.startSlide : currentSlideIndex;
        seekToSlidePaused(relative);
      }
      prevSlideIndexRef.current = currentSlideIndex;
    }
  }, [
    currentSlideIndex,
    playbackState,
    isClassPlaying,
    pause,
    consumeEngineDrivenSlideChange,
    seekToSlidePaused,
    sceneSlideBounds,
  ]);

  const speakingAgent = useMemo(
    () => (speakingAgentId ? agents.find((a) => a.id === speakingAgentId) || null : null),
    [agents, speakingAgentId],
  );

  // Determine scene id for whiteboard
  const sceneId = currentScene?.id || currentSlide?.id || 'default';

  // Audio URL — only used when the engine is NOT managing audio via speech
  // actions. When the engine has actions, it handles TTS audio internally
  // and the AudioPlayer must stay silent to avoid dual-audio overlap.
  const engineManagesAudio = hasScenes && currentSceneHasLinearPlayback;
  const audioUrl = engineManagesAudio
    ? undefined
    : currentScene?.content.type === 'slide'
      ? (currentScene.content as MAICSlideContent).audioUrl
      : currentSlide?.audioUrl;

  // ─── Discussion ──────────────────────────────────────────────────────
  // Discussion mode activates automatically when the engine fires a
  // `discussion` action during playback. There's no manual toggle button
  // anymore — the handler below just ends the current discussion and
  // resumes playback from the checkpoint.
  // Topic + participant ids fed into RoundtablePanel. Two writers:
  //   1. ProactiveCardManager → enterDiscussionFromProactiveCard wrapper
  //      (suggestion text + scene's multiAgent.agentIds, see below).
  //   2. handleDiscussionJoin (engine-driven gate) → values lifted from
  //      `discussionPending` BEFORE we clear it.
  // Without this the panel always fell back to the scene title and to
  // every agent in the classroom — unrelated to whatever the prompt
  // actually said.
  const [discussionTopic, setDiscussionTopic] = useState('');
  const [discussionAgentIds, setDiscussionAgentIds] = useState<string[]>([]);

  const toast = useToast();

  // T7.c — transient end-of-session flash card, rendered inside the
  // viewport. Used by handleCloseDiscussion below.
  const endFlash = useEndSessionFlash();

  // Porting P1.4 — engine fires a single window event when it falls back
  // to the reading-time timer because TTS is unavailable. We show one
  // info toast per classroom session so the user understands why audio
  // is missing instead of silently staring at mute agents.
  const ttsToastedRef = useRef(false);
  useEffect(() => {
    const onUnavail = () => {
      if (ttsToastedRef.current) return;
      ttsToastedRef.current = true;
      toast.info(
        'Audio unavailable',
        'Reading along — subtitles will still play.',
      );
    };
    window.addEventListener('maic:tts-unavailable', onUnavail);
    return () => window.removeEventListener('maic:tts-unavailable', onUnavail);
  }, [toast]);

  const handleCloseDiscussion = useCallback(() => {
    // Capture the kind BEFORE we null it so the flash shows the right copy.
    const kind = discussionMode ?? 'discussion';
    setDiscussionMode(null);
    resumeAfterDiscussion();
    // T7.c — transient "Discussion ended" flash. Toast is still helpful
    // for keyboard users and accessibility (role="status"), but the
    // flash is what's visually centered on the stage.
    endFlash.show(kind);
    toast.info('Discussion ended', 'Resuming the class');
  }, [discussionMode, setDiscussionMode, resumeAfterDiscussion, toast, endFlash]);

  // Porting P1.1 — Join/Skip on the engine-driven discussion gate.
  // Join promotes the pending state into the real discussion mode (the
  // engine is already paused, so RoundtablePanel just opens). Skip clears
  // the pending state and un-pauses the engine so playback continues
  // from the checkpoint the engine saved.
  const handleDiscussionJoin = useCallback(() => {
    if (!discussionPending) return;
    const sessionType = discussionPending.sessionType;
    // Capture topic + agentIds from the engine's pending payload BEFORE
    // we clear it; otherwise RoundtablePanel falls back to scene title.
    setDiscussionTopic(discussionPending.topic ?? '');
    setDiscussionAgentIds(discussionPending.agentIds ?? []);
    setDiscussionPending(null);
    setDiscussionMode(sessionType);
  }, [discussionPending, setDiscussionPending, setDiscussionMode]);
  const handleDiscussionSkip = useCallback(() => {
    setDiscussionPending(null);
    resumeAfterDiscussion();
  }, [setDiscussionPending, resumeAfterDiscussion]);

  // Wrapper for the proactive-card flow: capture the suggestion text +
  // scene agents into local state so RoundtablePanel reflects what was
  // actually clicked, then drop into the engine's discussion-pause path.
  const enterDiscussionFromProactiveCard = useCallback(
    (topic: string, agentIds: string[]) => {
      setDiscussionTopic(topic);
      setDiscussionAgentIds(agentIds);
      enterDiscussionFromUI();
    },
    [enterDiscussionFromUI],
  );

  // T6 — gate all scene-switch attempts on active discussion. When the
  // user clicks a scene chip or sidebar tile while a discussion is open,
  // we park the target and show a confirm instead of jumping silently.
  // `sceneIdx === -1` is a sentinel for "cancel pending only".
  const guardedSeekToScene = useCallback(
    (sceneIdx: number) => {
      if (discussionMode !== null) {
        setPendingSceneSwitch(sceneIdx);
        return;
      }
      seekToScene(sceneIdx);
    },
    [discussionMode, seekToScene],
  );
  const confirmSceneSwitch = useCallback(() => {
    const target = pendingSceneSwitch;
    setPendingSceneSwitch(null);
    if (target === null) return;
    // Close discussion first so resumeAfterDiscussion restores the old
    // checkpoint, then immediately hop to the new scene. `seekToScene`
    // calls `stop()` internally so the resumed audio is cancelled.
    setDiscussionMode(null);
    resumeAfterDiscussion();
    endFlash.show('discussion');
    seekToScene(target);
  }, [pendingSceneSwitch, setDiscussionMode, resumeAfterDiscussion, seekToScene, endFlash]);

  // ─── Playback Controls ───────────────────────────────────────────────
  const handlePlayPause = useCallback(() => {
    if (playbackState === 'playing') {
      pause();
    } else if (playbackState === 'paused') {
      resume();
    } else if (isClassPlaying) {
      playFromCurrent();
    } else {
      playFromCurrent();
    }
  }, [playbackState, isClassPlaying, pause, resume, playFromCurrent]);

  const handlePrevScene = useCallback(() => {
    if (currentSceneIndex > 0) {
      goToScene(currentSceneIndex - 1);
    }
  }, [currentSceneIndex, goToScene]);

  // ─── Fullscreen ──────────────────────────────────────────────────────
  // T7.d — on enter, also call `navigator.keyboard.lock(['Escape'])` so
  // pressing Escape during fullscreen dismisses our in-stage panels (help
  // overlay, discussion gate, chat) instead of auto-exiting fullscreen.
  // On exit, unlock. Feature-detected — Safari / Firefox silently no-op.
  const lockEscape = useCallback(() => {
    const kb = (navigator as Navigator & {
      keyboard?: { lock?: (keys: string[]) => Promise<void>; unlock?: () => void };
    }).keyboard;
    kb?.lock?.(['Escape']).catch(() => {
      /* permission denied / unsupported */
    });
  }, []);
  const unlockEscape = useCallback(() => {
    const kb = (navigator as Navigator & {
      keyboard?: { lock?: (keys: string[]) => Promise<void>; unlock?: () => void };
    }).keyboard;
    kb?.unlock?.();
  }, []);
  // Ref for the stage root — used both as the fullscreen target (so
  // mobile browser chrome doesn't obscure the stage) and as the DOM
  // node that gets portalled into the Document PiP window.
  const stageRootRef = useRef<HTMLDivElement>(null);

  // MOB-P0-3 — iPhone/iPod Safari exposes no standard Fullscreen API on
  // arbitrary elements (only `<video>` via `webkitEnterFullscreen`).
  // We feature-detect by checking for `requestFullscreen` on the document
  // element AND `document.fullscreenEnabled`. If neither exists on a
  // phone-sized iOS UA we hide the button entirely so the user doesn't
  // tap a no-op control. We intentionally skip iPad in this check because
  // modern iPadOS Safari does support element-level Fullscreen API.
  const fullscreenSupported = useMemo(() => {
    if (typeof document === 'undefined') return false;
    type FSDocument = Document & { fullscreenEnabled?: boolean };
    type FSElement = HTMLElement & { webkitRequestFullscreen?: () => void };
    const doc = document as FSDocument;
    const root = document.documentElement as FSElement;
    const hasApi =
      typeof root.requestFullscreen === 'function' ||
      typeof root.webkitRequestFullscreen === 'function';
    if (!hasApi) return false;
    // Explicit iPhone/iPod exclusion — iOS Safari lies by having some of
    // the prefixed symbols on the prototype but `fullscreenEnabled` is
    // false and `requestFullscreen()` rejects on <div>. This is the only
    // reliable sniff short of parsing the full UA.
    const isIphone =
      typeof navigator !== 'undefined' &&
      /iPhone|iPod/.test(navigator.userAgent) &&
      doc.fullscreenEnabled !== true;
    return !isIphone;
  }, []);

  const toggleFullscreen = useCallback(() => {
    // Vendor-prefixed type-escape hatches for Safari, iOS, and older
    // Edge. We try `requestFullscreen` on the stage element first so
    // the mobile browser nav bar doesn't overlap the player; fall back
    // to the document root if that isn't supported.
    type FSElement = HTMLElement & {
      webkitRequestFullscreen?: () => Promise<void> | void;
      webkitEnterFullscreen?: () => void;
      msRequestFullscreen?: () => Promise<void> | void;
    };
    type FSDocument = Document & {
      webkitFullscreenElement?: Element | null;
      webkitExitFullscreen?: () => Promise<void> | void;
      msExitFullscreen?: () => Promise<void> | void;
    };
    const doc = document as FSDocument;
    const inFullscreen = !!(document.fullscreenElement || doc.webkitFullscreenElement);

    if (!inFullscreen) {
      // MOB-P0-3 — Don't attempt anything on iPhone Safari. The button
      // is hidden via `fullscreenSupported`, but belt-and-suspenders.
      if (!fullscreenSupported) return;
      const target = (stageRootRef.current ?? document.documentElement) as FSElement;
      const request =
        target.requestFullscreen?.bind(target) ||
        target.webkitRequestFullscreen?.bind(target) ||
        target.msRequestFullscreen?.bind(target);
      if (request) {
        Promise.resolve(request())
          .then(() => {
            setFullscreen(true);
            lockEscape();
          })
          .catch(() => {
            // MOB-P0-3 — Never flip the UI into "fullscreen" when the
            // underlying API rejected the request.
          });
      }
      // Previously we tried `target.webkitEnterFullscreen()` here as an
      // iOS fallback; it's a <video>-only API and silently no-oped on
      // the stage <div>, then called setFullscreen(true) anyway. Removed.
    } else {
      const exit =
        document.exitFullscreen?.bind(document) ||
        doc.webkitExitFullscreen?.bind(doc) ||
        doc.msExitFullscreen?.bind(doc);
      if (exit) {
        Promise.resolve(exit())
          .then(() => {
            setFullscreen(false);
            unlockEscape();
          })
          .catch(() => {});
      } else {
        setFullscreen(false);
        unlockEscape();
      }
    }
  }, [setFullscreen, lockEscape, unlockEscape, fullscreenSupported]);
  // If the user exits fullscreen via the browser's own UI (F11, ESC on
  // some platforms that bypass our lock), keep isFullscreen in sync so
  // auto-hide controls don't stay hidden forever.
  useEffect(() => {
    const handler = () => {
      const doc = document as Document & { webkitFullscreenElement?: Element | null };
      const inFS = !!(document.fullscreenElement || doc.webkitFullscreenElement);
      if (!inFS && isFullscreen) {
        setFullscreen(false);
        unlockEscape();
      }
    };
    document.addEventListener('fullscreenchange', handler);
    // Safari / older WebKit use the vendor-prefixed event name.
    document.addEventListener('webkitfullscreenchange', handler as EventListener);
    return () => {
      document.removeEventListener('fullscreenchange', handler);
      document.removeEventListener('webkitfullscreenchange', handler as EventListener);
    };
  }, [isFullscreen, setFullscreen, unlockEscape]);

  // ─── Document Picture-in-Picture ─────────────────────────────────────
  // Desktop Chrome/Edge 116+. Hook returns isSupported=false on mobile
  // or any browser without the API, which causes StageToolbar to hide
  // the button entirely.
  const pip = useDocumentPiP();
  const isMobile = typeof navigator !== 'undefined'
    && /android|iphone|ipad|ipod|mobile/i.test(navigator.userAgent);
  const pipButtonVisible = pip.isSupported && !isMobile;
  const togglePiP = useCallback(() => {
    if (!pipButtonVisible) return;
    if (pip.isOpen) {
      pip.close();
    } else {
      void pip.open(stageRootRef);
    }
  }, [pip, pipButtonVisible]);

  // ─── Keyboard Shortcuts ──────────────────────────────────────────────
  useKeyboardShortcuts({
    onPlayPause: handlePlayPause,
    onNextScene: nextScene,
    onPrevScene: handlePrevScene,
    onToggleFullscreen: toggleFullscreen,
    onToggleChat: () => setShowChatPanel(!showChatPanel),
    onVolumeUp: () => setAudioVolume(Math.min(1, audioVolume + 0.1)),
    onVolumeDown: () => setAudioVolume(Math.max(0, audioVolume - 0.1)),
    onMute: () => setAudioVolume(audioVolume > 0 ? 0 : 0.8),
    onToggleSceneSidebar: () => setShowSceneSidebar((v) => !v),
    onShowHelp: () => setShowKeyboardHelp(true),
    onTogglePiP: pipButtonVisible ? togglePiP : undefined,
    enabled: true,
  });

  // ─── Keyboard modifier tracking (Ctrl/Shift/Space) ─────────────────
  useEffect(() => {
    const cleanup = initKeyboardListeners();
    return cleanup;
  }, []);

  // ─── Empty State ─────────────────────────────────────────────────────
  if (slides.length === 0 && scenes.length === 0) {
    return (
      <div className="flex items-center justify-center h-full bg-gray-50 text-gray-400">
        <p className="text-sm">No slides to display. Generate a classroom to begin.</p>
      </div>
    );
  }

  return (
    <div
      ref={stageRootRef}
      className={cn(
        'flex flex-col h-full w-full bg-gray-100 overflow-hidden',
        isFullscreen && 'fixed inset-0 z-50',
      )}
      role="main"
      aria-label="AI Classroom Stage"
    >
      {/* MOB-P0-8 — Screen-reader-only live region announcing the
          current scene. Rerenders whenever `currentSceneIndex` or the
          scene title changes so assistive tech ("Scene 3 of 8: Solving
          two-step equations") gets fresh feedback. `aria-live="polite"`
          so we don't interrupt playback narration. Kept outside tab
          order via `sr-only`. */}
      {hasScenes && (
        <div className="sr-only" role="status" aria-live="polite" aria-atomic="true">
          {`Scene ${currentSceneIndex + 1} of ${scenes.length}${
            currentScene?.title ? `: ${currentScene.title}` : ''
          }`}
        </div>
      )}

      {/* SPRINT-2-BATCH-9-F10 (TEST-P0-8) — terminal "classroom complete"
          announcement. Renders ONLY after the playback engine reaches the
          end of the last scene under autoplay. The stable
          `data-testid="classroom-complete"` lets the Playwright e2e suite
          assert genuine completion (not just `Scene N of N` in the live
          region). Cleared by every play/load/seek path in
          usePlaybackEngine, so it never appears on initial mount and never
          sticks across runs. `sr-only` + `role="status"` so assistive
          tech announces it without disturbing the visual layout. */}
      {classroomComplete && (
        <div
          className="sr-only"
          role="status"
          aria-live="polite"
          aria-atomic="true"
          data-testid="classroom-complete"
        >
          Class complete
        </div>
      )}

      {/* Top toolbar — Sprint 4 · B.7 auto-hides in fullscreen */}
      <div
        className={cn(
          'transition-opacity duration-300',
          controlsVisible ? 'opacity-100' : 'opacity-0 pointer-events-none',
        )}
      >
        <StageToolbar
          role={role}
          onToggleFullscreen={toggleFullscreen}
          fullscreenSupported={fullscreenSupported}
          pipSupported={pipButtonVisible}
          pipOpen={pip.isOpen}
          onTogglePiP={togglePiP}
          onToggleSceneSidebar={() => setShowSceneSidebar((v) => !v)}
        />
      </div>

      {/* Main content area */}
      <div className="flex flex-1 min-h-0 overflow-hidden relative" data-testid="maic-stage">
        {/* Scene sidebar (left) */}
        {hasScenes && (
          <SceneSidebar
            visible={showSceneSidebar}
            onClose={() => setShowSceneSidebar(false)}
            onSceneSelect={guardedSeekToScene}
          />
        )}

        {/* Viewport wrapper (flex-col to stack video + subtitles) */}
        <div className="flex-1 flex flex-col min-w-0">
          <div
            className="flex-1 relative flex flex-col items-center justify-center gap-2 bg-gray-900 p-2 sm:p-3 min-w-0"
            onTouchStart={handleTouchStart}
            onTouchEnd={handleTouchEnd}
          >
            {/* 16:9 aspect ratio container — fill available slide row only.
                The speaker/agent chrome has its own row below this, so it does
                not cover lesson text or image content on shorter viewports. */}
            <div className="relative flex-1 min-h-0 w-full flex items-center justify-center">
              <div className="relative w-full max-w-full max-h-full aspect-video bg-white rounded-lg shadow-lg overflow-hidden">
            {/* Scene-based rendering (preferred) */}
            {hasScenes && currentScene ? (
              <div className="absolute inset-0">
                <SceneRenderer scene={currentScene} mode="playback" role={role} imagesPending={imagesPending} />
              </div>
            ) : currentSlide ? (
              <div className="absolute inset-0">
                <SlideRenderer slide={currentSlide} />
              </div>
            ) : null}

            {/* Whiteboard layer — opens automatically when an agent fires
                a `wb_open` action during playback. No manual toggle.
                T7.b — wrapped in AnimatePresence so `showWhiteboard=false`
                plays the 500ms fade in Whiteboard.tsx's motion.div
                instead of snapping away. */}
            <AnimatePresence>
              {showWhiteboard && (
                <div key="wb-layer" className="absolute inset-0">
                  <Whiteboard sceneId={sceneId} readonly={true} />
                </div>
              )}
            </AnimatePresence>

            {/* Spotlight / Laser overlay */}
            <SpotlightOverlay
              active={spotlightActive}
              onToggle={() => setSpotlightActive(false)}
            />

            {/* Highlight overlay for element highlighting (driven by store) */}
            <HighlightOverlay
              elementId={spotlightElementId}
              active={!!spotlightElementId}
              onDismiss={() => setSpotlightElementId(null)}
            />

            {/* Laser pointer effect (driven by store) */}
            <LaserPointer
              active={!!laserElementId}
              targetElementId={laserElementId}
              color={laserColor || '#ef4444'}
            />

            {/* Resume chip — shows when a saved playback position is
                detected for this classroom. Hidden once the user either
                resumes or dismisses. */}
            {resumeTarget && (
              <div className="absolute top-3 left-1/2 -translate-x-1/2 z-40">
                <div className="flex items-center gap-2 rounded-full bg-black/75 backdrop-blur-md border border-white/10 px-3 py-1.5 shadow-lg">
                  <span className="text-xs text-white/90">
                    Continue from scene {resumeTarget.sceneIndex + 1}?
                  </span>
                  <button
                    type="button"
                    onClick={acceptResume}
                    className="rounded-full bg-white/95 text-gray-900 text-[11px] font-semibold px-2.5 py-0.5 hover:bg-white"
                  >
                    Continue
                  </button>
                  <button
                    type="button"
                    onClick={dismissResume}
                    className="text-[11px] text-white/60 hover:text-white/90 px-1"
                  >
                    Start over
                  </button>
                </div>
              </div>
            )}

            {/* Start Class overlay — T7.a: breathing play button.
                Opacity 50%→100% and scale 1.00→1.06 on a 1 s mirror loop
                while idle. On hover we lock to full opacity + lift the
                scale a touch so the CTA feels clickable. Matches
                OpenMAIC's `canvas-area.tsx:194-220` idle feel. */}
            {hasScenes &&
              currentSceneHasLinearPlayback &&
              playbackState === 'idle' &&
              !isClassPlaying && (
              <div className="absolute inset-0 z-30 flex items-center justify-center bg-black/25 backdrop-blur-sm">
                <button
                  onClick={playFromCurrent}
                  className="group flex flex-col items-center gap-3 px-8 py-6 rounded-2xl bg-white/95 shadow-xl hover:shadow-2xl transition-shadow"
                  aria-label={`Start playback — scene ${currentSceneIndex + 1} of ${scenes.length}, ${agents.length} agents`}
                >
                  <span
                    className="flex items-center justify-center h-16 w-16 rounded-full bg-indigo-600 shadow-lg transition-colors group-hover:bg-indigo-700"
                    style={{
                      animation: 'maic-breathe 1s ease-in-out infinite alternate',
                      transformOrigin: 'center',
                    }}
                  >
                    <svg className="h-8 w-8 text-white ml-1" fill="currentColor" viewBox="0 0 24 24">
                      <path d="M8 5v14l11-7z" />
                    </svg>
                  </span>
                  <span className="text-lg font-semibold text-gray-900">
                    {currentSceneIndex > 0 ? 'Start This Scene' : 'Start Class'}
                  </span>
                  <span className="text-xs text-gray-500">
                    {scenes.length} activit{scenes.length === 1 ? 'y' : 'ies'} &middot; {agents.length} agents
                  </span>
                </button>
                {/* Scoped keyframes so we don't pollute the global CSS.
                    The group-hover rule freezes the animation at full
                    opacity + scale for a grounded hover state. */}
                <style>{`
                  @keyframes maic-breathe {
                    from { opacity: 0.55; transform: scale(1); }
                    to   { opacity: 1;    transform: scale(1.06); }
                  }
                  .group:hover [style*="maic-breathe"] {
                    animation-play-state: paused !important;
                    opacity: 1 !important;
                    transform: scale(1.08) !important;
                  }
                `}</style>
              </div>
            )}

            {/* Discussion panel overlay */}
            {discussionMode && (
              <RoundtablePanel
                sessionType={discussionMode}
                topic={discussionTopic || currentScene?.title || 'Discussion'}
                agentIds={discussionAgentIds.length > 0 ? discussionAgentIds : agents.map((a) => a.id)}
                onClose={handleCloseDiscussion}
                role={role}
              />
            )}

            {/* Engine-driven discussion gate — shows the 3 s breath +
                Join/Skip countdown when the playback engine hits a
                scripted discussion action. See DiscussionGateCard for
                the state-machine explanation. */}
            <DiscussionGateCard
              onJoin={handleDiscussionJoin}
              onSkip={handleDiscussionSkip}
            />

            {/* T7.c — end-of-session flash, centered over the viewport
                for ~1.8s after a discussion closes. */}
            <EndSessionFlash kind={endFlash.kind} />

            {/* Proactive discussion suggestion cards — overlay inside the
                aspect-ratio viewport so they never overflow the stage or
                push past the scene navigator below. */}
            <div className="absolute inset-x-0 bottom-3 z-20 flex justify-center px-4 pointer-events-none max-h-[40%]">
              <ProactiveCardManager
                enabled={isClassPlaying && !discussionMode && !discussionPending}
                onBeforeDiscussion={enterDiscussionFromProactiveCard}
              />
            </div>
              </div>
            </div>

          <div className="relative h-20 w-full shrink-0">
            {/* Persistent roundtable strip — lives in the reserved stage chrome
                below the slide, so it never covers lesson text or images. */}
            {roundtableStripEnabled && (
              <RoundtableStrip
                agents={agents}
                speakingAgentId={speakingAgentId}
                isPlaying={isClassPlaying}
                hidden={!!discussionMode}
              />
            )}

            {/* Speaking agent overlay (bottom-left) */}
            <PresentationSpeechOverlay
              agent={speakingAgent}
              speechText={speechText}
              active={!!speakingAgent}
            />
          </div>

          {/* Export menu (teacher only) */}
          {role === 'teacher' && classroomId && (
            <div className="absolute top-2 right-2 z-20">
              <ExportMenu classroomId={classroomId} />
            </div>
          )}
          </div>
        </div>

        {/* Right sidebar (desktop): Chat + Lecture Notes tabs live inside ChatPanel */}
        {showChatPanel && classroomId && (
          <div className="hidden md:flex w-80 shrink-0 h-full">
            <ChatPanel
              role={role}
              classroomId={classroomId}
              onPlaybackInterrupt={handleUserInterrupt}
              onPlaybackResume={resumeAfterInterrupt}
            />
          </div>
        )}
      </div>

      {/*
        MOB-P0-2 (2026-04-23): mobile chat drawer. Previously chat was
        `hidden md:flex` only — Q&A feature was dead on every phone.
        Now phone users get a FAB (bottom-right) that opens a full-screen
        overlay. Same ChatPanel component, same store state — we just
        rearrange the container based on viewport.
      */}
      {classroomId && (
        <>
          {/* FAB — visible only on mobile, hides when the overlay is open. */}
          {!showChatPanel && (
            <button
              type="button"
              onClick={() => setShowChatPanel(true)}
              className={cn(
                'md:hidden fixed bottom-20 right-4 z-40',
                'h-12 w-12 rounded-full',
                'bg-primary-600 text-white shadow-lg',
                'flex items-center justify-center',
                'hover:bg-primary-700 active:scale-95 transition',
                'focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2',
              )}
              aria-label="Open classroom chat"
            >
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M8.625 12a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0H8.25m4.125 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0H12m4.125 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 0 1-2.555-.337A5.972 5.972 0 0 1 5.41 20.97a5.969 5.969 0 0 1-.474-.065 4.48 4.48 0 0 0 .978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25Z" />
              </svg>
            </button>
          )}

          {/* Mobile overlay — full-screen ChatPanel below md breakpoint. */}
          {showChatPanel && (
            <div
              className={cn(
                'md:hidden fixed inset-0 z-50',
                'bg-white flex flex-col',
              )}
              role="dialog"
              aria-modal="true"
              aria-label="Classroom chat"
            >
              <div className="flex items-center justify-between px-3 py-2 border-b border-gray-200">
                <span className="text-sm font-semibold text-gray-900">Chat</span>
                <button
                  type="button"
                  onClick={() => setShowChatPanel(false)}
                  className={cn(
                    'h-10 w-10 rounded-full flex items-center justify-center',
                    'text-gray-600 hover:bg-gray-100',
                    'focus:outline-none focus:ring-2 focus:ring-primary-500',
                  )}
                  aria-label="Close chat"
                >
                  <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
              <div className="flex-1 min-h-0">
                <ChatPanel
                  role={role}
                  classroomId={classroomId}
                  onPlaybackInterrupt={handleUserInterrupt}
                  onPlaybackResume={resumeAfterInterrupt}
                />
              </div>
            </div>
          )}
        </>
      )}

      {/* Bottom navigation bar — scene chips + canonical Play/Pause.
          Same auto-hide as the toolbar so fullscreen playback is clean. */}
      <div
        className={cn(
          'transition-opacity duration-300',
          controlsVisible ? 'opacity-100' : 'opacity-0 pointer-events-none',
        )}
      >
        <SlideNavigator onPlayPause={handlePlayPause} onSeekToScene={guardedSeekToScene} />
      </div>

      {/* Headless audio player */}
      <AudioPlayer audioUrl={audioUrl} />

      {/* Keyboard shortcut help overlay — Sprint 4 · B.13 */}
      <KeyboardHelpOverlay
        open={showKeyboardHelp}
        onClose={() => setShowKeyboardHelp(false)}
      />

      {/* T6 — confirm dialog: scene switch during an active discussion.
          "Cancel" keeps the discussion; "Confirm" closes it cleanly and
          jumps to the target scene. */}
      <ConfirmDialog
        isOpen={pendingSceneSwitch !== null}
        onClose={() => setPendingSceneSwitch(null)}
        onConfirm={confirmSceneSwitch}
        title="End discussion and switch scene?"
        message="A discussion is currently active. Switching will close it and take you to the new scene."
        confirmLabel="Switch scene"
        cancelLabel="Stay"
        variant="warning"
      />
    </div>
  );
};
