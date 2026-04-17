// src/pages/teacher/MAICPlayerPage.tsx
//
// Teacher AI Classroom player — loads classroom data from IndexedDB + API
// and renders the full Stage. Handles DRAFT/GENERATING/FAILED states gracefully.

import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { usePageTitle } from '../../hooks/usePageTitle';
import { maicApi } from '../../services/openmaicService';
import { useMAICStageStore } from '../../stores/maicStageStore';
import { getStoredClassroom, saveClassroom } from '../../lib/maicDb';
import { Stage } from '../../components/maic/Stage';

const ArrowLeftIcon = () => (
  <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5 3 12m0 0 7.5-7.5M3 12h18" />
  </svg>
);

export const MAICPlayerPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [storeReady, setStoreReady] = useState(false);
  const [hasContent, setHasContent] = useState(false);

  const setClassroomId = useMAICStageStore((s) => s.setClassroomId);
  const setSlides = useMAICStageStore((s) => s.setSlides);
  const setAgents = useMAICStageStore((s) => s.setAgents);
  const setChatMessages = useMAICStageStore((s) => s.setChatMessages);
  const setScenes = useMAICStageStore((s) => s.setScenes);
  const setSceneSlideBounds = useMAICStageStore((s) => s.setSceneSlideBounds);
  const reset = useMAICStageStore((s) => s.reset);

  const { data: classroom, isLoading, error } = useQuery({
    queryKey: ['maic-classroom', id],
    queryFn: async () => {
      const res = await maicApi.getClassroom(id!);
      return res.data;
    },
    enabled: !!id,
    // Poll while GENERATING so we can detect when it becomes READY
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === 'GENERATING' || status === 'DRAFT' ? 3000 : false;
    },
  });

  usePageTitle(classroom?.title || 'AI Classroom');

  // Load classroom content from IndexedDB into store.
  //
  // Freshness rule: the API's `updated_at` wins when it's newer than the
  // IndexedDB `syncedAt`. This prevents stale cached slides (with empty
  // image src or old agent rosters) from shadowing a re-generated
  // classroom whose backend record was refreshed after the user last
  // visited. The old code path used IndexedDB unconditionally, which
  // silently masked the image/voice fixes for anyone who had cached a
  // previous version.
  useEffect(() => {
    if (!classroom || !id) return;

    let cancelled = false;

    async function loadContent() {
      setClassroomId(id!);

      const stored = await getStoredClassroom(id!);
      if (cancelled) return;

      const meta = classroom as unknown as Record<string, unknown>;
      const apiContent = meta.content as {
        slides?: unknown[]; scenes?: unknown[]; sceneSlideBounds?: unknown[];
      } | undefined;
      const apiConfig = meta.config as { agents?: unknown[] } | undefined;
      const apiUpdatedAt = typeof meta.updated_at === 'string'
        ? new Date(meta.updated_at as string).getTime()
        : 0;

      const apiHasSlides = Array.isArray(apiContent?.slides) && (apiContent!.slides as unknown[]).length > 0;
      const cacheHasSlides = !!stored?.slides?.length;
      const apiIsNewer = apiUpdatedAt > 0 && (!stored?.syncedAt || apiUpdatedAt > stored.syncedAt);

      // Decision tree:
      //   1. API has content AND (no cache OR cache is older OR cache is empty)
      //      → use API, overwrite IndexedDB.
      //   2. Cache has slides AND API is stale/absent → use cache.
      //   3. Neither has slides → contentFound=false, page shows "Preparing".
      const useApi = apiHasSlides && (apiIsNewer || !cacheHasSlides);

      let contentFound = false;

      if (useApi && apiContent) {
        setSlides(apiContent.slides as Parameters<typeof setSlides>[0]);
        contentFound = true;
        if (apiContent.scenes?.length) {
          setScenes(apiContent.scenes as Parameters<typeof setScenes>[0]);
        }
        if (apiContent.sceneSlideBounds?.length) {
          setSceneSlideBounds(apiContent.sceneSlideBounds as Parameters<typeof setSceneSlideBounds>[0]);
        }
        if (apiConfig?.agents?.length) {
          setAgents(apiConfig.agents as Parameters<typeof setAgents>[0]);
        }
        // Preserve chat history from IndexedDB if present — session chat
        // is a per-user thing and the backend classroom record doesn't own it.
        if (stored?.chatHistory?.length) setChatMessages(stored.chatHistory);

        // Overwrite IndexedDB so future visits pick up the fresh copy.
        saveClassroom({
          id: id!,
          title: String(meta.title || ''),
          slides: (apiContent.slides || []) as Parameters<typeof setSlides>[0],
          scenes: (apiContent.scenes || []) as Parameters<typeof setScenes>[0],
          outlines: [],
          agents: (apiConfig?.agents || []) as Parameters<typeof setAgents>[0],
          chatHistory: stored?.chatHistory || [],
          audioCache: stored?.audioCache || {},
          config: stored?.config || {},
          sceneSlideBounds: (apiContent.sceneSlideBounds || []) as Parameters<typeof setSceneSlideBounds>[0],
          syncedAt: Date.now(),
        }).catch(() => {});
      } else if (cacheHasSlides && stored) {
        // Cache wins — API either has no content or is older.
        if (stored.slides?.length) { setSlides(stored.slides); contentFound = true; }
        if (stored.agents?.length) setAgents(stored.agents);
        if (stored.chatHistory?.length) setChatMessages(stored.chatHistory);
        if (stored.scenes?.length) { setScenes(stored.scenes); contentFound = true; }
        if (stored.sceneSlideBounds?.length) setSceneSlideBounds(stored.sceneSlideBounds);
      }

      setHasContent(contentFound);
      setStoreReady(true);
    }

    loadContent();

    return () => {
      cancelled = true;
      reset();
      setStoreReady(false);
      setHasContent(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [classroom, id]);

  // ─── Loading ─────────────────────────────────────────────────────────────────

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-indigo-600" />
      </div>
    );
  }

  // ─── Not Found ───────────────────────────────────────────────────────────────

  if (error || !classroom) {
    return (
      <div className="space-y-4 p-6">
        <button
          onClick={() => navigate('/teacher/ai-classroom')}
          className="flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900"
        >
          <ArrowLeftIcon />
          Back to Library
        </button>
        <div className="bg-red-50 border border-red-200 rounded-lg p-6 text-center">
          <h3 className="text-lg font-medium text-red-800 mb-2">Classroom Not Found</h3>
          <p className="text-sm text-red-600">
            This classroom could not be loaded. It may have been deleted or is not accessible.
          </p>
        </div>
      </div>
    );
  }

  // ─── FAILED status ───────────────────────────────────────────────────────────

  if (classroom.status === 'FAILED') {
    return (
      <div className="space-y-4 p-6">
        <button
          onClick={() => navigate('/teacher/ai-classroom')}
          className="flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900"
        >
          <ArrowLeftIcon />
          Back to Library
        </button>
        <div className="bg-red-50 border border-red-200 rounded-lg p-6 text-center">
          <h3 className="text-lg font-medium text-red-800 mb-2">Generation Failed</h3>
          <p className="text-sm text-red-600">
            {classroom.error_message || 'Something went wrong during classroom generation.'}
          </p>
          <button
            onClick={() => navigate('/teacher/ai-classroom/new')}
            className="mt-4 inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 transition-colors"
          >
            Try Again
          </button>
        </div>
      </div>
    );
  }

  // ─── DRAFT / GENERATING — show progress ──────────────────────────────────────

  if (classroom.status === 'DRAFT' || classroom.status === 'GENERATING') {
    // If we have content in IndexedDB (partial generation), show the Stage
    if (storeReady && hasContent) {
      return (
        <div className="flex flex-col h-[calc(100vh-80px)]">
          <div className="flex items-center gap-3 px-3 py-2 border-b border-gray-200 bg-white flex-shrink-0">
            <button
              onClick={() => navigate('/teacher/ai-classroom')}
              className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
              title="Back to Library"
            >
              <ArrowLeftIcon />
            </button>
            <div className="min-w-0 flex-1">
              <h1 className="text-sm font-semibold text-gray-900 truncate">
                {classroom.title}
              </h1>
            </div>
            <span className="shrink-0 text-xs font-medium px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 animate-pulse">
              Generating...
            </span>
          </div>
          <div className="flex-1 min-h-0">
            <Stage role="teacher" />
          </div>
        </div>
      );
    }

    // No content yet — show honest generation progress.
    // `scene_count` is stamped by the worker as scenes finish, giving us a
    // real ordinal to display without needing a separate status endpoint.
    // The outer query already polls every 3s while GENERATING.
    const meta = classroom as unknown as Record<string, unknown>;
    const plannedScenes =
      (meta.expected_scenes as number | undefined) ??
      ((meta.config as { sceneCount?: number } | undefined)?.sceneCount) ??
      undefined;
    const doneScenes = (meta.scene_count as number | undefined) ?? 0;
    const createdAt = meta.created_at as string | undefined;
    const elapsedMs = createdAt ? Date.now() - new Date(createdAt).getTime() : 0;
    const elapsedMin = Math.floor(elapsedMs / 60000);
    const elapsedSec = Math.floor((elapsedMs % 60000) / 1000);

    return (
      <div className="space-y-4 p-6">
        <button
          onClick={() => navigate('/teacher/ai-classroom')}
          className="flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900"
        >
          <ArrowLeftIcon />
          Back to Library
        </button>
        <div className="max-w-md mx-auto text-center py-16 space-y-6">
          <div className="inline-flex items-center justify-center h-20 w-20 rounded-full bg-indigo-50 mx-auto">
            <svg className="h-10 w-10 text-indigo-500 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          </div>
          <div>
            <h2 className="text-xl font-semibold text-gray-900 mb-2">
              {classroom.status === 'GENERATING'
                ? 'Generating your classroom'
                : 'Preparing classroom'}
            </h2>
            <p className="text-sm text-gray-500">
              AI agents are composing slides, scripts, and interactive content.
              Full classrooms typically take <span className="font-medium">5–10 minutes</span>.
            </p>
          </div>
          {plannedScenes && (
            <div className="max-w-xs mx-auto">
              <div className="flex items-center justify-between text-[11px] text-gray-400 mb-1 tabular-nums">
                <span>
                  {doneScenes} of {plannedScenes} scenes ready
                </span>
                <span>
                  {createdAt ? `Elapsed ${elapsedMin}m ${elapsedSec.toString().padStart(2, '0')}s` : ''}
                </span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-1.5 overflow-hidden">
                <div
                  className="bg-indigo-500 h-1.5 rounded-full transition-all duration-700"
                  style={{
                    width: `${Math.min(100, Math.round((doneScenes / plannedScenes) * 100))}%`,
                  }}
                />
              </div>
            </div>
          )}
          <p className="text-xs text-gray-400">
            Safe to leave this tab — we'll refresh this page the moment it's ready.
          </p>
        </div>
      </div>
    );
  }

  // ─── ARCHIVED ────────────────────────────────────────────────────────────────

  if (classroom.status === 'ARCHIVED') {
    return (
      <div className="space-y-4 p-6">
        <button
          onClick={() => navigate('/teacher/ai-classroom')}
          className="flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900"
        >
          <ArrowLeftIcon />
          Back to Library
        </button>
        <div className="bg-gray-50 border border-gray-200 rounded-lg p-6 text-center">
          <h3 className="text-lg font-medium text-gray-700 mb-2">Classroom Archived</h3>
          <p className="text-sm text-gray-500">
            This classroom has been archived and is no longer accessible.
          </p>
        </div>
      </div>
    );
  }

  // ─── READY — wait for store to hydrate ───────────────────────────────────────

  if (!storeReady) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-indigo-600" />
      </div>
    );
  }

  // ─── READY — full Stage ──────────────────────────────────────────────────────

  return (
    <div className="flex flex-col h-[calc(100vh-80px)]">
      <div className="flex items-center gap-3 px-3 py-2 border-b border-gray-200 bg-white flex-shrink-0">
        <button
          onClick={() => navigate('/teacher/ai-classroom')}
          className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
          title="Back to Library"
        >
          <ArrowLeftIcon />
        </button>
        <div className="min-w-0 flex-1">
          <h1 className="text-sm font-semibold text-gray-900 truncate">
            {classroom.title}
          </h1>
        </div>
      </div>
      <div className="flex-1 min-h-0">
        <Stage role="teacher" />
      </div>
    </div>
  );
};
