// src/pages/teacher/MAICPlayerPage.tsx
//
// Teacher AI Classroom player — loads classroom data from IndexedDB + API
// and renders the full Stage. Handles DRAFT/GENERATING/FAILED states gracefully.

import React, { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { usePageTitle } from '../../hooks/usePageTitle';
import { maicApi } from '../../services/openmaicService';
import { useMAICStageStore } from '../../stores/maicStageStore';
import { getStoredClassroom, saveClassroom } from '../../lib/maicDb';
import { Stage } from '../../components/maic/Stage';
import { computeRefetchInterval } from '../../lib/maicPollingPolicy';

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

  // Track the previous images_pending value so we can detect the
  // true→false flip and force a slide-asset refresh.
  const prevImagesPendingRef = useRef<boolean | undefined>(undefined);

  const { data: classroom, isLoading, error, refetch } = useQuery({
    queryKey: ['maic-classroom', id],
    queryFn: async () => {
      const res = await maicApi.getClassroom(id!);
      return res.data;
    },
    enabled: !!id,
    // PERF-P0-2 (2026-04-23): polling was a fixed 3s while GENERATING with
    // no backoff, no stop-on-stall, no pause-on-hidden. At 100 teachers
    // that's ~33 RPS against classroom-detail — wasteful for stalled runs,
    // unnecessary for hidden tabs.
    //
    // SPRINT-2-BATCH-5-F7/F8: logic extracted to lib/maicPollingPolicy.ts
    // so both this component and its tests import the same source of truth.
    // The F7 stall detector stops the 5s images_pending poll after 10 min.
    refetchInterval: (query) => computeRefetchInterval(
      query.state.data as { status?: string; images_pending?: boolean; updated_at?: string; progress?: { last_progress_at?: string | null } } | undefined,
    ),
    refetchIntervalInBackground: false,
  });

  // CG-P0-3: When images_pending flips true → false, the Celery task has
  // finished filling all image src URLs. The polled classroom object
  // already carries updated slide content (with real image srcs) — push
  // it directly into the store without a full reset (preserves chat
  // history). Also overwrite IndexedDB so future visits see real images.
  useEffect(() => {
    if (!classroom) return;
    const meta = classroom as unknown as Record<string, unknown>;
    const currentPending = meta.images_pending as boolean | undefined;
    const prev = prevImagesPendingRef.current;

    if (prev === true && currentPending === false) {
      // The polled payload has the freshly-filled slides — push them
      // into the store directly so ImageElement re-renders with real srcs.
      const apiContent = meta.content as {
        slides?: unknown[]; scenes?: unknown[]; sceneSlideBounds?: unknown[];
      } | undefined;
      if (apiContent?.slides?.length) {
        setSlides(apiContent.slides as Parameters<typeof setSlides>[0]);
      }
      if (apiContent?.scenes?.length) {
        setScenes(apiContent.scenes as Parameters<typeof setScenes>[0]);
      }
      // Overwrite IndexedDB with the image-filled payload so the next
      // visit doesn't show empty-src slides.
      const apiConfig = meta.config as { agents?: unknown[] } | undefined;
      const stored = getStoredClassroom(id!);
      stored.then((s) => {
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

  // SPRINT-2-BATCH-5-F7: detect when the images_pending poll has stalled.
  // computeRefetchInterval returns `false` when updated_at is >10min old,
  // which stops the interval — but the component doesn't know WHY it stopped.
  // Here we mirror the stall condition and set imagesStalled so the UI can
  // surface the "image fetching is taking unusually long" banner.
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

      // T1 — if the store already has scenes for THIS classroom (i.e.
      // the user opened the classroom mid-generation via the wizard's
      // "Open classroom now" button and the loop is still writing),
      // skip the API/IndexedDB overwrite so we don't clobber live
      // partial state. The wizard's generation loop continues to push
      // scenes into the same store; Stage.tsx re-renders as they land.
      const storeState = useMAICStageStore.getState();
      if (
        storeState.classroomId === id &&
        storeState.scenes.length > 0 &&
        classroom?.status === 'GENERATING'
      ) {
        setStoreReady(true);
        setHasContent(true);
        return;
      }

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
    // Depend on classroom?.id, NOT the whole classroom object — React
    // Query emits a fresh object reference on every refetch (window
    // focus, interval) even when nothing changed. Using the whole
    // object as a dep fires the cleanup (reset() wipes the store)
    // after every refetch, which was making the AI Tutor chat
    // disappear mid-conversation as soon as any refetch happened.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [classroom?.id, id]);

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
        // MOB-P0-4 — `100dvh` (dynamic viewport height) avoids the iOS URL-bar
        // jump that `100vh` hits when Safari hides its bottom chrome on scroll.
        <div className="flex flex-col h-[calc(100dvh-80px)]">
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
            <Stage role="teacher" imagesPending={
              !!((classroom as unknown as Record<string, unknown>).images_pending)
            } />
          </div>
        </div>
      );
    }

    // No content yet — show honest generation progress.
    // Prefer live server-stamped progress from `progress.*` (set by the
    // wizard's pingClassroomProgress calls and by the update endpoint's
    // auto-heartbeat on partial content saves). Fall back to legacy
    // scene_count + created_at for classrooms generated before the
    // progress fields existed.
    const meta = classroom as unknown as Record<string, unknown>;
    const progress = (meta.progress ?? {}) as {
      phase?: '' | 'outline' | 'content' | 'actions' | 'saving' | 'complete';
      phase_scene_index?: number;
      scenes_ready?: number;
      expected_scenes?: number | null;
      started_at?: string | null;
      last_progress_at?: string | null;
    };
    const plannedScenes =
      progress.expected_scenes ??
      ((meta.config as { sceneCount?: number } | undefined)?.sceneCount) ??
      undefined;
    const doneScenes =
      progress.scenes_ready ??
      (meta.scene_count as number | undefined) ??
      0;
    const createdAt = meta.created_at as string | undefined;
    // Elapsed timer: server-reported started_at is the truth once
    // generation has produced any progress; fall back to row creation
    // (original behavior) so already-in-flight rows still show a timer.
    const startRef = progress.started_at ?? createdAt;
    const elapsedMs = startRef ? Date.now() - new Date(startRef).getTime() : 0;
    const elapsedMin = Math.floor(elapsedMs / 60000);
    const elapsedSec = Math.floor((elapsedMs % 60000) / 1000);
    // Stalled detection: if we have a last_progress_at and it's older
    // than 3 minutes, the wizard/worker has almost certainly died.
    // Keeps the UI honest — no more forever-spinning "Generating...".
    const STALE_MS = 3 * 60 * 1000;
    const lastProgressMs = progress.last_progress_at
      ? Date.now() - new Date(progress.last_progress_at).getTime()
      : null;
    const isStalled =
      classroom.status === 'GENERATING' &&
      lastProgressMs !== null &&
      lastProgressMs > STALE_MS;

    const phaseLabel: Record<string, string> = {
      outline: 'Generating outline…',
      content: plannedScenes
        ? `Generating scene ${progress.phase_scene_index ?? 1} of ${plannedScenes} — content`
        : 'Generating scene content…',
      actions: plannedScenes
        ? `Generating scene ${progress.phase_scene_index ?? 1} of ${plannedScenes} — actions`
        : 'Generating scene actions…',
      saving: 'Saving…',
      complete: 'Finishing up…',
    };
    const currentPhaseText =
      (progress.phase && phaseLabel[progress.phase]) ||
      'AI agents are composing slides, scripts, and interactive content.';

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
          <div
            className={`inline-flex items-center justify-center h-20 w-20 rounded-full mx-auto ${
              isStalled ? 'bg-amber-50' : 'bg-indigo-50'
            }`}
          >
            {isStalled ? (
              <svg className="h-10 w-10 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            ) : (
              <svg className="h-10 w-10 text-indigo-500 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
            )}
          </div>
          <div>
            <h2 className="text-xl font-semibold text-gray-900 mb-2">
              {isStalled
                ? 'Generation appears stalled'
                : classroom.status === 'GENERATING'
                  ? 'Generating your classroom'
                  : 'Preparing classroom'}
            </h2>
            <p className="text-sm text-gray-500">
              {isStalled
                ? `No progress for ${Math.floor((lastProgressMs ?? 0) / 60000)}m. The wizard tab may have closed or the LLM stalled. You can delete this classroom and start a new one.`
                : currentPhaseText}
            </p>
            {!isStalled && classroom.status === 'GENERATING' && (
              <p className="text-sm text-gray-500 mt-1">
                Full classrooms typically take <span className="font-medium">5–10 minutes</span>.
              </p>
            )}
          </div>
          {plannedScenes && (
            <div className="max-w-xs mx-auto">
              <div className="flex items-center justify-between text-[11px] text-gray-400 mb-1 tabular-nums">
                <span>
                  {doneScenes} of {plannedScenes} scenes ready
                </span>
                <span>
                  {startRef ? `Elapsed ${elapsedMin}m ${elapsedSec.toString().padStart(2, '0')}s` : ''}
                </span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-1.5 overflow-hidden">
                <div
                  className={`h-1.5 rounded-full transition-all duration-700 ${
                    isStalled ? 'bg-amber-400' : 'bg-indigo-500'
                  }`}
                  style={{
                    width: `${Math.min(100, Math.round((doneScenes / plannedScenes) * 100))}%`,
                  }}
                />
              </div>
            </div>
          )}
          {isStalled ? (
            <StallActions
              classroomId={classroom.id}
              savedSceneCount={(meta.scene_count as number | undefined) ?? 0}
              onFinalized={() => refetch()}
              onBack={() => navigate('/teacher/ai-classroom')}
            />
          ) : (
            <p className="text-xs text-gray-400">
              Safe to leave this tab — we'll refresh this page the moment it's ready.
            </p>
          )}
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

  // CG-P0-3: extract images_pending from the polled classroom so the Stage
  // can show the "fetching image…" skeleton on slides with empty src.
  const imagesPending = !!(
    (classroom as unknown as Record<string, unknown>).images_pending
  );

  // CG-P1-9 (2026-04-28): hold the Stage on a "preparing classroom" panel
  // while `images_pending=true`. Previously we let users into the player
  // immediately on `status=READY`, which exposed empty-src image elements
  // as "Fetching image…" skeletons mid-playback — a bad first impression.
  // Polling (computeRefetchInterval) drives the unblock automatically when
  // Celery finishes fill_classroom_images. The existing F7 stall banner +
  // 10-min stall detector still cover the "Celery crashed" failure mode.
  if (!storeReady || (imagesPending && !imagesStalled)) {
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

  // ─── READY — full Stage ──────────────────────────────────────────────────────

  return (
    // MOB-P0-4 — `100dvh` (dynamic viewport height) avoids the iOS URL-bar
    // jump that `100vh` hits when Safari hides its bottom chrome on scroll.
    <div className="flex flex-col h-[calc(100dvh-80px)]">
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
        {imagesPending && (
          <span className="shrink-0 text-xs font-medium px-2 py-0.5 rounded-full bg-blue-50 text-blue-600 animate-pulse">
            Fetching images…
          </span>
        )}
      </div>
      {/* SPRINT-2-BATCH-5-F7: stall banner — shown when images_pending has
          been true for >10min without flipping false, meaning the Celery
          fill_classroom_images task probably crashed before completing. */}
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
      <div className="flex-1 min-h-0">
        <Stage role="teacher" imagesPending={imagesPending} />
      </div>
    </div>
  );
};

// ─── Stall recovery actions ────────────────────────────────────────────────
//
// CG-P0-8: when the wizard tab reloaded mid-generation, the row sits on
// `status=GENERATING` with content_scenes already partially saved by the
// per-scene persistPartial PATCH (CG-P0-4). The stall panel offers two
// recovery paths instead of forcing the user to delete and start over:
//   1. "Use what's saved (N scenes)" — calls finalize-partial → READY.
//      Visible only when the row has at least 1 saved scene.
//   2. "Back to library" — always available; user can delete from there.

interface StallActionsProps {
  classroomId: string;
  savedSceneCount: number;
  onFinalized: () => void;
  onBack: () => void;
}

const StallActions: React.FC<StallActionsProps> = ({
  classroomId,
  savedSceneCount,
  onFinalized,
  onBack,
}) => {
  const [isFinalizing, setIsFinalizing] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const canFinalize = savedSceneCount > 0;

  const handleFinalize = async () => {
    setIsFinalizing(true);
    setErrorMsg(null);
    try {
      const res = await maicApi.finalizePartialClassroom(classroomId);
      if (!res.data.ok) {
        setErrorMsg(res.data.error || 'Could not finalize this classroom.');
        return;
      }
      // Refetch — when status flips to READY, MAICPlayerPage re-renders
      // into the player view automatically.
      onFinalized();
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Finalize request failed.';
      setErrorMsg(msg);
    } finally {
      setIsFinalizing(false);
    }
  };

  return (
    <div className="flex flex-col items-center gap-3">
      {canFinalize && (
        <button
          onClick={handleFinalize}
          disabled={isFinalizing}
          className="rounded-lg px-4 py-2 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 disabled:cursor-wait transition-colors"
        >
          {isFinalizing
            ? 'Finalizing…'
            : `Use what's saved (${savedSceneCount} scene${savedSceneCount === 1 ? '' : 's'})`}
        </button>
      )}
      <button
        onClick={onBack}
        className="text-sm font-medium text-amber-700 hover:text-amber-800"
      >
        Back to library
      </button>
      {errorMsg && (
        <p className="text-xs text-red-600 max-w-sm text-center">{errorMsg}</p>
      )}
    </div>
  );
};
