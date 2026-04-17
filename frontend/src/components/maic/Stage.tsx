// src/components/maic/Stage.tsx
//
// Main container component for the MAIC AI Classroom player. Composes
// SceneRenderer, Whiteboard, ChatPanel, SlideNavigator, StageToolbar,
// AgentAvatar, AudioPlayer, SpotlightOverlay,
// RoundtablePanel, ExportMenu, SceneSidebar, and keyboard shortcuts
// into a unified interactive stage.

import React, { useState, useMemo, useCallback, useEffect, useRef } from 'react';
import { useMAICStageStore } from '../../stores/maicStageStore';
import { useMAICSettingsStore } from '../../stores/maicSettingsStore';
import { initKeyboardListeners } from '../../stores/maicKeyboardStore';
import { usePlaybackEngine } from '../../hooks/usePlaybackEngine';
import { useKeyboardShortcuts } from '../../hooks/useKeyboardShortcuts';
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
import { HighlightOverlay } from './HighlightOverlay';
import { LaserPointer } from './LaserPointer';
import { cn } from '../../lib/utils';

interface StageProps {
  role: MAICPlayerRole;
}

export const Stage: React.FC<StageProps> = ({ role }) => {
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
  const nextScene = useMAICStageStore((s) => s.nextScene);
  const goToScene = useMAICStageStore((s) => s.goToScene);

  const goToSlide = useMAICStageStore((s) => s.goToSlide);

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
    pause,
    resume,
    loadScene,
    resumeAfterDiscussion,
    startClass,
    playFromCurrent,
    seekToScene,
    consumeEngineDrivenSlideChange,
  } = usePlaybackEngine(role);

  // Current scene & slide
  const hasScenes = scenes.length > 0;
  const currentScene = scenes[currentSceneIndex] || null;
  const currentSlide = slides[currentSlideIndex] || null;

  // Load scene actions when scene changes
  useEffect(() => {
    if (currentScene) {
      loadScene(currentScene);
    }
  }, [currentScene, loadScene]);

  // Stop current audio when user MANUALLY navigates to a different slide.
  // Skip the auto-pause when the slide change was engine-driven —
  //   a) during autoplay the engine's executeTransition changes the slide
  //      between actions (covered by isClassPlaying),
  //   b) when seekToSlide is called from a thumbnail click the hook sets
  //      a consume-once flag (covered by consumeEngineDrivenSlideChange).
  // Only user-driven changes (prev/next buttons, keyboard shortcuts) should
  // pause the engine.
  const prevSlideIndexRef = useRef(currentSlideIndex);
  useEffect(() => {
    if (prevSlideIndexRef.current !== currentSlideIndex) {
      const engineDriven = consumeEngineDrivenSlideChange();
      if (!engineDriven && !isClassPlaying && playbackState === 'playing') {
        pause();
      }
      prevSlideIndexRef.current = currentSlideIndex;
    }
  }, [currentSlideIndex, playbackState, isClassPlaying, pause, consumeEngineDrivenSlideChange]);

  const speakingAgent = useMemo(
    () => (speakingAgentId ? agents.find((a) => a.id === speakingAgentId) || null : null),
    [agents, speakingAgentId],
  );

  // Determine scene id for whiteboard
  const sceneId = currentScene?.id || currentSlide?.id || 'default';

  // Audio URL — only used when the engine is NOT managing audio via speech
  // actions. When the engine has actions, it handles TTS audio internally
  // and the AudioPlayer must stay silent to avoid dual-audio overlap.
  const engineManagesAudio = hasScenes && (currentScene?.actions?.length ?? 0) > 0;
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
  const [discussionTopic] = useState('');
  const [discussionAgentIds] = useState<string[]>([]);

  const handleCloseDiscussion = useCallback(() => {
    setDiscussionMode(null);
    resumeAfterDiscussion();
  }, [setDiscussionMode, resumeAfterDiscussion]);

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
  const toggleFullscreen = useCallback(() => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen().then(() => setFullscreen(true)).catch(() => {});
    } else {
      document.exitFullscreen().then(() => setFullscreen(false)).catch(() => {});
    }
  }, [setFullscreen]);

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
      className={cn(
        'flex flex-col h-full w-full bg-gray-100 overflow-hidden',
        isFullscreen && 'fixed inset-0 z-50',
      )}
      role="main"
      aria-label="AI Classroom Stage"
    >
      {/* Top toolbar */}
      <StageToolbar role={role} />

      {/* Main content area */}
      <div className="flex flex-1 min-h-0 overflow-hidden relative" data-testid="maic-stage">
        {/* Scene sidebar (left) */}
        {hasScenes && (
          <SceneSidebar
            visible={showSceneSidebar}
            onClose={() => setShowSceneSidebar(false)}
          />
        )}

        {/* Viewport wrapper (flex-col to stack video + subtitles) */}
        <div className="flex-1 flex flex-col min-w-0">
        <div
          className="flex-1 relative flex items-center justify-center bg-gray-900 p-2 sm:p-3 min-w-0"
          onTouchStart={handleTouchStart}
          onTouchEnd={handleTouchEnd}
        >
          {/* 16:9 aspect ratio container — fill viewport as much as possible */}
          <div className="relative w-full max-w-[95vw] max-h-[calc(100%-0.5rem)] aspect-video bg-white rounded-lg shadow-lg overflow-hidden">
            {/* Scene-based rendering (preferred) */}
            {hasScenes && currentScene ? (
              <div className="absolute inset-0">
                <SceneRenderer scene={currentScene} mode="playback" role={role} />
              </div>
            ) : currentSlide ? (
              <div className="absolute inset-0">
                <SlideRenderer slide={currentSlide} />
              </div>
            ) : null}

            {/* Whiteboard layer — opens automatically when an agent fires
                a `wb_open` action during playback. No manual toggle. */}
            {showWhiteboard && (
              <div className="absolute inset-0">
                <Whiteboard sceneId={sceneId} readonly={true} />
              </div>
            )}

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
              color={laserColor || '#ef4444'}
            />

            {/* Start Class overlay — shows when class hasn't started */}
            {hasScenes && playbackState === 'idle' && !isClassPlaying && (
              <div className="absolute inset-0 z-30 flex items-center justify-center bg-black/40 backdrop-blur-sm">
                <button
                  onClick={startClass}
                  className="group flex flex-col items-center gap-3 px-8 py-6 rounded-2xl bg-white/95 shadow-xl hover:shadow-2xl transition-all hover:scale-105"
                >
                  <div className="flex items-center justify-center h-16 w-16 rounded-full bg-indigo-600 group-hover:bg-indigo-700 transition-colors shadow-lg">
                    <svg className="h-8 w-8 text-white ml-1" fill="currentColor" viewBox="0 0 24 24">
                      <path d="M8 5v14l11-7z" />
                    </svg>
                  </div>
                  <span className="text-lg font-semibold text-gray-900">Start Class</span>
                  <span className="text-xs text-gray-500">
                    {scenes.length} scenes &middot; {agents.length} agents
                  </span>
                </button>
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

            {/* Proactive discussion suggestion cards — overlay inside the
                aspect-ratio viewport so they never overflow the stage or
                push past the scene navigator below. */}
            <div className="absolute inset-x-0 bottom-3 z-20 flex justify-center px-4 pointer-events-none max-h-[40%]">
              <ProactiveCardManager
                enabled={isClassPlaying && !discussionMode}
              />
            </div>
          </div>

          {/* Speaking agent overlay (bottom-left) */}
          <PresentationSpeechOverlay
            agent={speakingAgent}
            speechText={speechText}
            active={!!speakingAgent}
          />

          {/* Export menu (teacher only) */}
          {role === 'teacher' && classroomId && (
            <div className="absolute top-2 right-2 z-20">
              <ExportMenu classroomId={classroomId} />
            </div>
          )}
        </div>
        </div>

        {/* Right sidebar: Chat + Lecture Notes tabs live inside ChatPanel */}
        {showChatPanel && classroomId && (
          <div className="hidden md:flex w-80 shrink-0 h-full">
            <ChatPanel role={role} classroomId={classroomId} />
          </div>
        )}
      </div>

      {/* Bottom navigation bar — scene chips + canonical Play/Pause */}
      <SlideNavigator onPlayPause={handlePlayPause} onSeekToScene={seekToScene} />

      {/* Headless audio player */}
      <AudioPlayer audioUrl={audioUrl} />
    </div>
  );
};
