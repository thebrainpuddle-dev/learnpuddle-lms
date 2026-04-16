// src/components/maic/Stage.tsx
//
// Main container component for the MAIC AI Classroom player. Composes
// SceneRenderer, Whiteboard, ChatPanel, SlideNavigator, StageToolbar,
// AgentAvatar, AudioPlayer, SpotlightOverlay, SpeechSubtitles,
// RoundtablePanel, ExportMenu, SceneSidebar, and keyboard shortcuts
// into a unified interactive stage.

import React, { useState, useMemo, useCallback, useEffect, useRef } from 'react';
import { Pencil } from 'lucide-react';
import { useMAICStageStore } from '../../stores/maicStageStore';
import { useMAICSettingsStore } from '../../stores/maicSettingsStore';
import { initKeyboardListeners } from '../../stores/maicKeyboardStore';
import { usePlaybackEngine } from '../../hooks/usePlaybackEngine';
import { useKeyboardShortcuts } from '../../hooks/useKeyboardShortcuts';
import type { MAICPlayerRole, MAICSlide } from '../../types/maic';
import type { MAICSlideContent } from '../../types/maic-scenes';
import { SceneRenderer } from './SceneRenderer';
import { SlideRenderer } from './SlideRenderer';
import { SlideEditor } from './slide-editor';
import { Whiteboard } from './Whiteboard';
import { ChatPanel } from './ChatPanel';
import { SlideNavigator } from './SlideNavigator';
import { StageToolbar } from './StageToolbar';
import { PresentationSpeechOverlay } from './PresentationSpeechOverlay';
import { AudioPlayer } from './AudioPlayer';
import { SpotlightOverlay } from './SpotlightOverlay';
import { SpeechSubtitles } from './SpeechSubtitles';
import { RoundtablePanel } from './RoundtablePanel';
import { ExportMenu } from './ExportMenu';
import { SceneSidebar } from './SceneSidebar';
import { NotesPanel } from './NotesPanel';
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
  const viewMode = useMAICStageStore((s) => s.viewMode);
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

  const showNotesPanel = useMAICStageStore((s) => s.showNotesPanel);
  const toggleNotesPanel = useMAICStageStore((s) => s.toggleNotesPanel);
  const goToSlide = useMAICStageStore((s) => s.goToSlide);

  const showChatPanel = useMAICSettingsStore((s) => s.showChatPanel);
  const setShowChatPanel = useMAICSettingsStore((s) => s.setShowChatPanel);
  const showWhiteboard = useMAICSettingsStore((s) => s.showWhiteboard);
  const setShowWhiteboard = useMAICSettingsStore((s) => s.setShowWhiteboard);
  const audioVolume = useMAICSettingsStore((s) => s.audioVolume);
  const setAudioVolume = useMAICSettingsStore((s) => s.setAudioVolume);

  const spotlightElementId = useMAICStageStore((s) => s.spotlightElementId);
  const setSpotlightElementId = useMAICStageStore((s) => s.setSpotlightElementId);
  const laserElementId = useMAICStageStore((s) => s.laserElementId);
  const laserColor = useMAICStageStore((s) => s.laserColor);

  const [spotlightActive, setSpotlightActive] = useState(false);
  const [showSceneSidebar, setShowSceneSidebar] = useState(false);
  const [editMode, setEditMode] = useState(false);

  const setSlides = useMAICStageStore((s) => s.setSlides);

  // ─── Slide Editor ─────────────────────────────────────────────────
  const handleSlideUpdate = useCallback(
    (updatedSlide: MAICSlide) => {
      const newSlides = slides.map((s) =>
        s.id === updatedSlide.id ? updatedSlide : s,
      );
      setSlides(newSlides);
    },
    [slides, setSlides],
  );

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

  // Playback engine
  const {
    playbackState,
    isClassPlaying,
    play,
    pause,
    resume,
    loadScene,
    resumeAfterDiscussion,
    startClass,
    playFromCurrent,
    stopClass,
    seekToSlide,
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

  // Stop current audio when user manually navigates to a different slide
  const prevSlideIndexRef = useRef(currentSlideIndex);
  useEffect(() => {
    if (prevSlideIndexRef.current !== currentSlideIndex) {
      // Slide changed — stop any playing audio so old speech doesn't persist
      if (playbackState === 'playing') {
        pause();
      }
      prevSlideIndexRef.current = currentSlideIndex;
    }
  }, [currentSlideIndex, playbackState, pause]);

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
  const [discussionTopic, setDiscussionTopic] = useState('');
  const [discussionAgentIds, setDiscussionAgentIds] = useState<string[]>([]);

  const handleCloseDiscussion = useCallback(() => {
    setDiscussionMode(null);
    setDiscussionTopic('');
    setDiscussionAgentIds([]);
    // Resume playback from the checkpoint saved when discussion was triggered
    resumeAfterDiscussion();
  }, [setDiscussionMode, resumeAfterDiscussion]);

  const handleToggleDiscussion = useCallback(() => {
    if (discussionMode) {
      handleCloseDiscussion();
    } else {
      setDiscussionMode('roundtable');
      setDiscussionTopic(currentScene?.title || 'Open Discussion');
      setDiscussionAgentIds(agents.map((a) => a.id));
    }
  }, [discussionMode, handleCloseDiscussion, setDiscussionMode, currentScene, agents]);

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
    onToggleWhiteboard: () => setShowWhiteboard(!showWhiteboard),
    onVolumeUp: () => setAudioVolume(Math.min(1, audioVolume + 0.1)),
    onVolumeDown: () => setAudioVolume(Math.max(0, audioVolume - 0.1)),
    onMute: () => setAudioVolume(audioVolume > 0 ? 0 : 0.8),
    onToggleSceneSidebar: () => setShowSceneSidebar((v) => !v),
    onToggleDiscussion: handleToggleDiscussion,
    onToggleNotes: toggleNotesPanel,
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
      <StageToolbar
        role={role}
        onDiscussionToggle={handleToggleDiscussion}
        discussionActive={!!discussionMode}
        onPlayPause={handlePlayPause}
        onStop={stopClass}
      />

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
            {/* Edit mode: render SlideEditor (teacher only) */}
            {editMode && role === 'teacher' && currentSlide ? (
              <div className="absolute inset-0">
                <SlideEditor
                  slide={currentSlide}
                  onSlideUpdate={handleSlideUpdate}
                />
              </div>
            ) : (
              <>
                {/* Scene-based rendering (preferred) */}
                {hasScenes && currentScene ? (
                  <div className="absolute inset-0">
                    <SceneRenderer scene={currentScene} mode="playback" role={role} />
                  </div>
                ) : (viewMode === 'slides' || viewMode === 'split') && currentSlide ? (
                  <div className={cn('absolute inset-0', viewMode === 'split' && 'w-1/2')}>
                    <SlideRenderer slide={currentSlide} />
                  </div>
                ) : null}
              </>
            )}

            {/* Whiteboard layer (hidden in edit mode) */}
            {!editMode && (viewMode === 'whiteboard' || viewMode === 'split' || showWhiteboard) && (
              <div className={cn(
                'absolute inset-0',
                viewMode === 'split' && !hasScenes && 'left-1/2 w-1/2 border-l border-gray-300',
              )}>
                {viewMode === 'split' && !hasScenes && (
                  <div className="absolute inset-0 bg-white" />
                )}
                <Whiteboard sceneId={sceneId} readonly={role === 'student'} />
              </div>
            )}

            {/* Whiteboard overlay for teacher annotations on slides */}
            {!editMode && !showWhiteboard && viewMode === 'slides' && role === 'teacher' && !hasScenes && (
              <Whiteboard sceneId={sceneId} readonly={false} />
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
          </div>

          {/* Speaking agent overlay (bottom-left) */}
          <PresentationSpeechOverlay
            agent={speakingAgent}
            speechText={speechText}
            active={!!speakingAgent}
          />

          {/* Edit mode toggle (teacher only) */}
          {role === 'teacher' && currentSlide && (
            <button
              onClick={() => setEditMode((v) => !v)}
              title={editMode ? 'Exit edit mode' : 'Edit slide'}
              className={cn(
                'absolute top-2 right-14 z-20 p-2 rounded-lg transition-colors shadow-sm',
                editMode
                  ? 'bg-blue-600 text-white hover:bg-blue-700'
                  : 'bg-white/90 text-gray-600 hover:bg-white hover:text-gray-900',
              )}
            >
              <Pencil className="w-4 h-4" />
            </button>
          )}

          {/* Export menu (teacher only) */}
          {role === 'teacher' && classroomId && (
            <div className="absolute top-2 right-2 z-20">
              <ExportMenu classroomId={classroomId} />
            </div>
          )}
        </div>

          {/* Speech subtitles (below the video viewport) */}
          <SpeechSubtitles
            text={speechText}
            agentName={speakingAgent?.name}
            agentColor={speakingAgent?.color}
          />

          {/* Proactive discussion suggestion cards */}
          <ProactiveCardManager
            enabled={isClassPlaying && !discussionMode}
          />
        </div>

        {/* Right sidebar panels */}
        {(showChatPanel || showNotesPanel) && (
          <div className="hidden md:flex flex-col shrink-0">
            {showChatPanel && classroomId && (
              <div className={cn('flex w-80', showNotesPanel ? 'flex-1 min-h-0' : 'h-full')}>
                <ChatPanel role={role} classroomId={classroomId} />
              </div>
            )}
            {showNotesPanel && (
              <div className={cn('flex', showChatPanel ? 'h-1/2 border-t border-gray-200' : 'h-full')}>
                <NotesPanel />
              </div>
            )}
          </div>
        )}
      </div>

      {/* Bottom navigation bar */}
      <SlideNavigator onSlideClick={seekToSlide} />

      {/* Headless audio player */}
      <AudioPlayer audioUrl={audioUrl} />
    </div>
  );
};
