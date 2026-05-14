// src/pages/student/MAICPlayerPage.tsx
//
// Student AI Classroom player — loads classroom data and renders the Stage
// in student mode (read-only whiteboard, no edit controls).

import React, { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { usePageTitle } from '../../hooks/usePageTitle';
import { maicStudentApi } from '../../services/openmaicService';
import { useMAICStageStore } from '../../stores/maicStageStore';
import { getStoredClassroom, saveClassroom } from '../../lib/maicDb';
import { Stage } from '../../components/maic/Stage';
import { computeRefetchInterval } from '../../lib/maicPollingPolicy';
import { useMaicMediaGenerationStore } from '../../stores/maicMediaGenerationStore';
import { useMaicClassroomChannel } from '../../hooks/useMaicClassroomChannel';
import { isClassroomPlayable } from '../../lib/maicReadinessGate';

const ArrowLeftIcon = () => (
  <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5 3 12m0 0 7.5-7.5M3 12h18" />
  </svg>
);

export const StudentMAICPlayerPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [storeReady, setStoreReady] = useState(false);
  // SPRINT-2-BATCH-5-F7: true when images_pending has been true for >10min
  // without flipping false (Celery task stalled or OOM-killed).
  const [imagesStalled, setImagesStalled] = useState(false);

  const setClassroomId = useMAICStageStore((s) => s.setClassroomId);
  const setSlides = useMAICStageStore((s) => s.setSlides);
  const setAgents = useMAICStageStore((s) => s.setAgents);
  const setChatMessages = useMAICStageStore((s) => s.setChatMessages);
  const setScenes = useMAICStageStore((s) => s.setScenes);
  const setSceneSlideBounds = useMAICStageStore((s) => s.setSceneSlideBounds);
  const reset = useMAICStageStore((s) => s.reset);

  // CG-P0-3: track images_pending flip to push refreshed slide assets
  // when the Celery fill task completes.
  const prevImagesPendingRef = useRef<boolean | undefined>(undefined);

  // F2 (P0): per-element media-task store hooks (mirrors teacher player).
  const hydrateMediaTasks = useMaicMediaGenerationStore((s) => s.hydrateFromMap);
  const clearMediaTasksForStage = useMaicMediaGenerationStore(
    (s) => s.clearStage,
  );
  // F3 readiness gate input: subscribed at top of the component so the hook
  // call is unconditional (must run before any early `return` below).
  const mediaTasksForGate = useMaicMediaGenerationStore((s) => s.tasks);

  const { data: classroom, isLoading, error, refetch } = useQuery({
    queryKey: ['student-maic-classroom', id],
    queryFn: async () => {
      const res = await maicStudentApi.getClassroom(id!);
      return res.data;
    },
    enabled: !!id,
    // SPRINT-2-BATCH-5-F7/F8: delegate to shared computeRefetchInterval
    // from lib/maicPollingPolicy.ts so both teacher + student players share
    // identical logic, and tests import the same source of truth.
    refetchInterval: (query) => computeRefetchInterval(
      query.state.data as { status?: string; images_pending?: boolean; updated_at?: string; progress?: { last_progress_at?: string | null } } | undefined,
    ),
    refetchIntervalInBackground: false,
  });

  // CG-P0-3: push freshly-filled slide assets into the store when
  // images_pending flips true → false (mirrors teacher player logic).
  useEffect(() => {
    if (!classroom) return;
    const meta = classroom as unknown as Record<string, unknown>;
    const currentPending = meta.images_pending as boolean | undefined;
    const prev = prevImagesPendingRef.current;

    if (prev === true && currentPending === false) {
      const apiContent = meta.content as {
        slides?: unknown[]; scenes?: unknown[]; sceneSlideBounds?: unknown[];
      } | undefined;
      // R4: setSlides/setScenes both reset currentSlideIndex/currentSceneIndex
      // to 0; preserve position so an in-flight class isn't yanked back to
      // slide 0 (and the slide-change effect doesn't auto-pause the engine)
      // when Celery completes the image fill mid-playback.
      const storeBefore = useMAICStageStore.getState();
      const prevSceneIdx = storeBefore.currentSceneIndex;
      const prevSlideIdx = storeBefore.currentSlideIndex;
      if (apiContent?.slides?.length) {
        setSlides(apiContent.slides as Parameters<typeof setSlides>[0]);
      }
      if (apiContent?.scenes?.length) {
        setScenes(apiContent.scenes as Parameters<typeof setScenes>[0]);
      }
      useMAICStageStore.setState({
        currentSceneIndex: prevSceneIdx,
        currentSlideIndex: prevSlideIdx,
      });
      const apiConfig = meta.config as { agents?: unknown[] } | undefined;
      getStoredClassroom(id!).then((s) => {
        saveClassroom({
          id: id!,
          title: String(meta.title || ''),
          slides: (apiContent?.slides || []) as Parameters<typeof setSlides>[0],
          scenes: (apiContent?.scenes || []) as Parameters<typeof setScenes>[0],
          outlines: [],
          agents: (apiConfig?.agents || []) as Parameters<typeof setAgents>[0],
          chatHistory: s?.chatHistory || [],
          config: s?.config || {},
          sceneSlideBounds: (apiContent?.sceneSlideBounds || []) as Parameters<typeof setSceneSlideBounds>[0],
          syncedAt: Date.now(),
        }).catch(() => {});
      }).catch(() => {});
    }

    prevImagesPendingRef.current = currentPending;
  }, [classroom, id, setSlides, setScenes, setSceneSlideBounds, setAgents]);

  // F2 (P0): hydrate the per-element media-task store from the GET response,
  // mount the WS channel, and clear on unmount. See teacher player for the
  // detailed rationale; this mirrors that flow exactly.
  useEffect(() => {
    if (!classroom || !id) return;
    const meta = classroom as unknown as Record<string, unknown>;
    const tasksMap = (meta.content_image_tasks ?? {}) as Parameters<
      typeof hydrateMediaTasks
    >[1];
    hydrateMediaTasks(id, tasksMap);
  }, [classroom, id, hydrateMediaTasks]);

  useMaicClassroomChannel(id ?? null);

  useEffect(() => {
    return () => {
      if (id) clearMediaTasksForStage(id);
    };
  }, [id, clearMediaTasksForStage]);

  // SPRINT-2-BATCH-5-F7: detect stalled images_pending (mirrors teacher player).
  useEffect(() => {
    if (!classroom) return;
    const meta = classroom as unknown as Record<string, unknown>;
    const pending = meta.images_pending as boolean | undefined;
    if (pending !== true) {
      setImagesStalled(false);
      return;
    }
    const updatedAt = meta.updated_at as string | undefined;
    if (!updatedAt) return;
    const ageMs = Date.now() - new Date(updatedAt).getTime();
    if (ageMs > 10 * 60 * 1000) {
      setImagesStalled(true);
    }
  }, [classroom]);

  usePageTitle(classroom?.title || 'AI Classroom');

  // Load classroom content — API updated_at wins over stale IndexedDB.
  // Same freshness logic as the teacher player; see MAICPlayerPage for
  // the rationale.
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
      const useApi = apiHasSlides && (apiIsNewer || !cacheHasSlides);

      if (useApi && apiContent) {
        setSlides(apiContent.slides as Parameters<typeof setSlides>[0]);
        if (apiContent.scenes?.length) setScenes(apiContent.scenes as Parameters<typeof setScenes>[0]);
        if (apiContent.sceneSlideBounds?.length) setSceneSlideBounds(apiContent.sceneSlideBounds as Parameters<typeof setSceneSlideBounds>[0]);
        if (apiConfig?.agents?.length) setAgents(apiConfig.agents as Parameters<typeof setAgents>[0]);
        if (stored?.chatHistory?.length) setChatMessages(stored.chatHistory);

        saveClassroom({
          id: id!,
          title: String(meta.title || ''),
          slides: (apiContent.slides || []) as Parameters<typeof setSlides>[0],
          scenes: (apiContent.scenes || []) as Parameters<typeof setScenes>[0],
          outlines: [],
          agents: (apiConfig?.agents || []) as Parameters<typeof setAgents>[0],
          chatHistory: stored?.chatHistory || [],
          config: stored?.config || {},
          sceneSlideBounds: (apiContent.sceneSlideBounds || []) as Parameters<typeof setSceneSlideBounds>[0],
          syncedAt: Date.now(),
        }).catch(() => {});
      } else if (cacheHasSlides && stored) {
        if (stored.slides?.length) setSlides(stored.slides);
        if (stored.agents?.length) setAgents(stored.agents);
        if (stored.chatHistory?.length) setChatMessages(stored.chatHistory);
        if (stored.scenes?.length) setScenes(stored.scenes);
        if (stored.sceneSlideBounds?.length) setSceneSlideBounds(stored.sceneSlideBounds);
      }

      setStoreReady(true);
    }

    loadContent();

    return () => {
      cancelled = true;
      reset();
      setStoreReady(false);
    };
    // Dep on classroom?.id only — see teacher MAICPlayerPage for the
    // full reasoning. tl;dr: React Query refetches produce new
    // classroom references that wipe the store mid-chat.
  }, [classroom?.id, id]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-indigo-600" />
      </div>
    );
  }

  if (error || !classroom) {
    return (
      <div className="space-y-4">
        <button
          onClick={() => navigate('/student/ai-classroom')}
          className="flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900"
        >
          <ArrowLeftIcon />
          Back to Classrooms
        </button>
        <div className="bg-red-50 border border-red-200 rounded-lg p-6 text-center">
          <h3 className="text-lg font-medium text-red-800 mb-2">Classroom Not Found</h3>
          <p className="text-sm text-red-600">
            This classroom could not be loaded. It may not be available.
          </p>
        </div>
      </div>
    );
  }

  if (classroom.status !== 'READY') {
    return (
      <div className="space-y-4">
        <button
          onClick={() => navigate('/student/ai-classroom')}
          className="flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900"
        >
          <ArrowLeftIcon />
          Back to Classrooms
        </button>
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-6 text-center">
          <h3 className="text-lg font-medium text-amber-800 mb-2">
            Classroom Not Available
          </h3>
          <p className="text-sm text-amber-600">
            This classroom is not yet ready. Please check back later.
          </p>
        </div>
      </div>
    );
  }

  // CG-P0-3: extract images_pending for the Stage skeleton indicator.
  const imagesPending = !!(
    (classroom as unknown as Record<string, unknown>).images_pending
  );

  // F3 (P0): two-milestone gate — mirrors the teacher player. With F2's
  // per-element media-task store hydrated, scene 0 ready is enough to
  // mount the Stage; remaining scenes stream in behind the scenes. For
  // legacy classrooms (empty `content_image_tasks` map) this falls back
  // to gating on `!imagesPending`. The classroom-level `images_pending`
  // boolean keeps driving polling and the Stage's per-image skeleton
  // until the whole batch is done. The F7 stall override skips the gate
  // when Celery looks crashed (>10min stuck).
  const playable = isClassroomPlayable({
    tasks: mediaTasksForGate,
    imagesPending,
  });

  if (!storeReady || (!playable && !imagesStalled)) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-indigo-600" />
        {imagesPending && (
          <p className="text-sm text-gray-500">
            Finishing up — fetching slide images…
          </p>
        )}
      </div>
    );
  }

  return (
    // MOB-P0-4 — `100dvh` (dynamic viewport height) avoids the iOS URL-bar
    // jump that `100vh` hits when Safari hides its bottom chrome on scroll.
    <div className="flex flex-col h-[calc(100dvh-80px)]">
      {/* Minimal header */}
      <div className="flex items-center gap-3 px-3 py-2 border-b border-gray-200 bg-white flex-shrink-0">
        <button
          onClick={() => navigate('/student/ai-classroom')}
          className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
          title="Back to Classrooms"
        >
          <ArrowLeftIcon />
        </button>
        <div className="min-w-0 flex-1">
          <h1 className="text-sm font-semibold text-gray-900 truncate">
            {classroom.title}
          </h1>
        </div>
      </div>

      {/* SPRINT-2-BATCH-5-F7: stall banner — mirrors teacher player. */}
      {imagesStalled && (
        <div
          data-testid="images-stall-banner"
          className="flex items-center gap-2 px-3 py-2 bg-amber-50 border-b border-amber-200 text-sm text-amber-800"
          role="alert"
        >
          <svg className="h-4 w-4 shrink-0 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <span className="flex-1">
            Image fetching is taking unusually long. Refresh to retry.
          </span>
          <button
            onClick={() => { setImagesStalled(false); refetch(); }}
            className="shrink-0 text-xs font-medium px-2 py-1 rounded bg-amber-100 hover:bg-amber-200 transition-colors cursor-pointer"
          >
            Refresh
          </button>
        </div>
      )}
      {/* Full Stage in student mode */}
      <div className="flex-1 min-h-0">
        <Stage role="student" imagesPending={imagesPending} />
      </div>
    </div>
  );
};
