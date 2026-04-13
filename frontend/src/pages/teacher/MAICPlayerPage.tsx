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
import { getStoredClassroom } from '../../lib/maicDb';
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

  // Load classroom content from IndexedDB into store
  useEffect(() => {
    if (!classroom || !id) return;

    let cancelled = false;

    async function loadContent() {
      setClassroomId(id!);

      const stored = await getStoredClassroom(id!);
      if (cancelled) return;

      let contentFound = false;

      if (stored) {
        if (stored.slides?.length) { setSlides(stored.slides); contentFound = true; }
        if (stored.agents?.length) setAgents(stored.agents);
        if (stored.chatHistory?.length) setChatMessages(stored.chatHistory);
        if (stored.scenes?.length) { setScenes(stored.scenes); contentFound = true; }
      }

      // Fallback: scenes from API response
      if (!stored?.scenes?.length) {
        const meta = classroom as unknown as Record<string, unknown>;
        if (meta.scenes && Array.isArray(meta.scenes)) {
          setScenes(meta.scenes as Parameters<typeof setScenes>[0]);
          contentFound = true;
        }
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

    // No content yet — show generation progress
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
                ? 'Generating Your Classroom'
                : 'Preparing Classroom'}
            </h2>
            <p className="text-sm text-gray-500">
              AI agents are creating slides, scripts, and interactive content.
              This may take a minute or two.
            </p>
          </div>
          <div className="max-w-xs mx-auto">
            <div className="w-full bg-gray-200 rounded-full h-1.5 overflow-hidden">
              <div className="bg-indigo-500 h-1.5 rounded-full animate-pulse" style={{ width: '60%' }} />
            </div>
          </div>
          <p className="text-xs text-gray-400">
            This page will update automatically when ready.
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
