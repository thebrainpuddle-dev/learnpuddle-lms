// src/pages/student/MAICPlayerPage.tsx
//
// Student AI Classroom player — loads classroom data and renders the Stage
// in student mode (read-only whiteboard, no edit controls).

import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { usePageTitle } from '../../hooks/usePageTitle';
import { maicStudentApi } from '../../services/openmaicService';
import { useMAICStageStore } from '../../stores/maicStageStore';
import { getStoredClassroom } from '../../lib/maicDb';
import { Stage } from '../../components/maic/Stage';

const ArrowLeftIcon = () => (
  <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5 3 12m0 0 7.5-7.5M3 12h18" />
  </svg>
);

export const StudentMAICPlayerPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [storeReady, setStoreReady] = useState(false);

  const setClassroomId = useMAICStageStore((s) => s.setClassroomId);
  const setSlides = useMAICStageStore((s) => s.setSlides);
  const setAgents = useMAICStageStore((s) => s.setAgents);
  const setChatMessages = useMAICStageStore((s) => s.setChatMessages);
  const setScenes = useMAICStageStore((s) => s.setScenes);
  const reset = useMAICStageStore((s) => s.reset);

  const { data: classroom, isLoading, error } = useQuery({
    queryKey: ['student-maic-classroom', id],
    queryFn: async () => {
      const res = await maicStudentApi.getClassroom(id!);
      return res.data;
    },
    enabled: !!id,
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

      if (stored) {
        if (stored.slides?.length) setSlides(stored.slides);
        if (stored.agents?.length) setAgents(stored.agents);
        if (stored.chatHistory?.length) setChatMessages(stored.chatHistory);
        if (stored.scenes?.length) setScenes(stored.scenes);
      }

      // Fallback: if API response includes scenes and IDB didn't have them
      if (!stored?.scenes?.length) {
        const meta = classroom as unknown as Record<string, unknown>;
        if (meta.scenes && Array.isArray(meta.scenes)) {
          setScenes(meta.scenes as Parameters<typeof setScenes>[0]);
        }
      }

      setStoreReady(true);
    }

    loadContent();

    return () => {
      cancelled = true;
      reset();
      setStoreReady(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [classroom, id]);

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

  if (!storeReady) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-indigo-600" />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-[calc(100vh-80px)]">
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

      {/* Full Stage in student mode */}
      <div className="flex-1 min-h-0">
        <Stage role="student" />
      </div>
    </div>
  );
};
