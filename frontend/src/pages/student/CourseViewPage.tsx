// src/pages/student/CourseViewPage.tsx
//
// Student course detail — split-pane layout with content player and module sidebar.

import React, { useState, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ContentPlayer } from '../../components/teacher';
import { ChatWidget } from '../../components/ai/ChatWidget';
import type { ContentContext } from '../../components/ai/ChatWidget';
import { CompletionRing } from '../../components/teacher/dashboard/CompletionRing';
import { studentService } from '../../services/studentService';
import type { StudentCourseDetail } from '../../services/studentService';
import {
  ArrowLeftIcon,
  PlayCircleIcon,
  DocumentTextIcon,
  LinkIcon,
  Bars3BottomLeftIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  LockClosedIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import { CheckCircleIcon as CheckCircleSolidIcon } from '@heroicons/react/24/solid';
import { cn } from '../../design-system/theme/cn';
import { usePageTitle } from '../../hooks/usePageTitle';
import { useToast } from '../../components/common';

type ContentItem = StudentCourseDetail['modules'][number]['contents'][number];

const contentTypeLabel = (type: ContentItem['content_type']) => {
  if (type === 'VIDEO') return 'Video';
  if (type === 'DOCUMENT') return 'Reading';
  if (type === 'LINK') return 'Link';
  if (type === 'AI_CLASSROOM') return 'AI Classroom';
  if (type === 'CHATBOT') return 'AI Chatbot';
  return 'Reading';
};

const formatDuration = (seconds?: number | null) => {
  if (!seconds || seconds <= 0) return '';
  const mins = Math.max(1, Math.round(seconds / 60));
  return `${mins} min`;
};

export const CourseViewPage: React.FC = () => {
  usePageTitle('Course');
  const { courseId } = useParams<{ courseId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const toast = useToast();

  const [expandedModules, setExpandedModules] = useState<string[]>([]);
  const [selectedContent, setSelectedContent] = useState<ContentItem | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(() =>
    typeof window !== 'undefined' && typeof window.matchMedia === 'function'
      ? window.matchMedia('(min-width: 1024px)').matches
      : true,
  );
  const lastSavedRef = useRef<number>(0);
  const startedContentRef = useRef<Set<string>>(new Set());

  // ── Video progress throttle (every 5 seconds) ──────────────────────────────
  const handleProgressUpdate = useCallback(
    async (seconds: number) => {
      if (!selectedContent || selectedContent.content_type !== 'VIDEO') return;
      if (seconds - lastSavedRef.current < 5) return;
      lastSavedRef.current = seconds;
      try {
        await studentService.updateContentProgress(selectedContent.id, {
          video_progress_seconds: seconds,
        });
        queryClient.invalidateQueries({ queryKey: ['studentCourse', courseId] });
        queryClient.invalidateQueries({ queryKey: ['studentDashboard'] });
        queryClient.invalidateQueries({ queryKey: ['studentCourses'] });
      } catch {
        // Silent fail; progress will retry on next tick.
      }
    },
    [selectedContent, queryClient, courseId],
  );

  // Reset saved-progress counter when content changes
  React.useEffect(() => {
    lastSavedRef.current = 0;
  }, [selectedContent?.id]);

  // ── Track content start ────────────────────────────────────────────────────
  React.useEffect(() => {
    if (!selectedContent || selectedContent.is_locked || selectedContent.is_completed) return;
    if (startedContentRef.current.has(selectedContent.id)) return;
    if (selectedContent.status === 'IN_PROGRESS') {
      startedContentRef.current.add(selectedContent.id);
      return;
    }
    startedContentRef.current.add(selectedContent.id);
    studentService.startContentProgress(selectedContent.id).catch(() => {
      // Silent fail
    });
  }, [selectedContent]);

  // ── Responsive sidebar auto-open ───────────────────────────────────────────
  React.useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return undefined;
    const media = window.matchMedia('(min-width: 1024px)');
    const onChange = (event: MediaQueryListEvent) => {
      if (event.matches) setSidebarOpen(true);
    };
    if (media.addEventListener) {
      media.addEventListener('change', onChange);
      return () => media.removeEventListener('change', onChange);
    }
    media.addListener(onChange);
    return () => media.removeListener(onChange);
  }, []);

  // ── Fetch course ──────────────────────────────────────────────────────────
  const { data: course, isLoading } = useQuery<StudentCourseDetail>({
    queryKey: ['studentCourse', courseId],
    enabled: Boolean(courseId),
    queryFn: () => studentService.getStudentCourseDetail(courseId as string),
  });

  // ── Auto-select first incomplete content & expand its module ──────────────
  React.useEffect(() => {
    if (!course?.modules) return;
    const unlockedModules = course.modules.filter((module) => !module.is_locked);
    const firstTargetModule =
      unlockedModules.find((module) => !module.is_completed) || unlockedModules[0] || course.modules[0];

    if (!firstTargetModule) return;
    setExpandedModules([firstTargetModule.id]);

    setSelectedContent((current) => {
      if (
        current &&
        !current.is_locked &&
        course.modules.some((module) => module.contents.some((item) => item.id === current.id))
      ) {
        return current;
      }
      const firstIncompleteUnlockedContent = firstTargetModule.contents.find(
        (item) => !item.is_locked && !item.is_completed,
      );
      const firstUnlockedContent = firstTargetModule.contents.find((item) => !item.is_locked);
      return firstIncompleteUnlockedContent || firstUnlockedContent || firstTargetModule.contents[0] || null;
    });
  }, [course]);

  // ── Flat content sequence for next-item navigation ─────────────────────────
  const flatContentSequence = React.useMemo(() => {
    if (!course) return [] as Array<ContentItem & { moduleId: string }>;
    return course.modules.flatMap((module) =>
      module.contents
        .slice()
        .sort((a, b) => a.order - b.order)
        .map((content) => ({ ...content, moduleId: module.id })),
    );
  }, [course]);

  const nextUnlockedContent = React.useMemo(() => {
    if (!selectedContent) return null;
    const currentIndex = flatContentSequence.findIndex((item) => item.id === selectedContent.id);
    if (currentIndex < 0) return null;
    for (let idx = currentIndex + 1; idx < flatContentSequence.length; idx += 1) {
      if (!flatContentSequence[idx].is_locked) return flatContentSequence[idx];
    }
    return null;
  }, [selectedContent, flatContentSequence]);

  const chatContentContext: ContentContext | null = null;

  // ── Shared completion handler ──────────────────────────────────────────────
  const handleComplete = useCallback(async () => {
    if (!selectedContent) return;
    try {
      await studentService.completeContent(selectedContent.id);
      await queryClient.invalidateQueries({ queryKey: ['studentCourse', courseId] });
      await queryClient.invalidateQueries({ queryKey: ['studentDashboard'] });
      await queryClient.invalidateQueries({ queryKey: ['studentCourses'] });
    } catch (error: any) {
      const reason = error?.response?.data?.error || 'This content is locked.';
      toast.error('Content Locked', reason);
    }
  }, [selectedContent, queryClient, courseId, toast]);

  // ── Sidebar helpers ────────────────────────────────────────────────────────
  const toggleModule = (moduleId: string) => {
    setExpandedModules((previous) =>
      previous.includes(moduleId) ? previous.filter((id) => id !== moduleId) : [...previous, moduleId],
    );
  };

  const getContentIcon = (type: string, isCompleted: boolean, isLocked: boolean) => {
    if (isLocked) return <LockClosedIcon className="h-4 w-4 text-slate-400" />;
    if (isCompleted) return <CheckCircleSolidIcon className="h-4 w-4 text-emerald-500" />;
    if (type === 'VIDEO') return <PlayCircleIcon className="h-4 w-4 text-slate-500" />;
    if (type === 'DOCUMENT') return <DocumentTextIcon className="h-4 w-4 text-slate-500" />;
    if (type === 'LINK') return <LinkIcon className="h-4 w-4 text-slate-500" />;
    return <DocumentTextIcon className="h-4 w-4 text-slate-500" />;
  };

  const handleNextItem = () => {
    if (nextUnlockedContent) {
      setSelectedContent(nextUnlockedContent);
      setExpandedModules((prev) =>
        prev.includes(nextUnlockedContent.moduleId) ? prev : [...prev, nextUnlockedContent.moduleId],
      );
    }
  };

  // ── Loading state ──────────────────────────────────────────────────────────
  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-500"></div>
      </div>
    );
  }

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="flex h-[calc(100dvh-6.5rem)] flex-col lg:h-[calc(100vh-8rem)]">
      {/* ── Top bar ────────────────────────────────────────────────────────── */}
      <div className="flex flex-col gap-3 border-b border-slate-200 pb-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-center">
          <button
            onClick={() => navigate('/student/courses')}
            className="mr-3 p-2 text-slate-500 hover:text-slate-700 hover:bg-slate-100 rounded-lg"
            aria-label="Back to my courses"
          >
            <ArrowLeftIcon className="h-5 w-5" />
          </button>
          <div className="min-w-0">
            <h1 className="truncate text-lg font-semibold text-slate-900 sm:text-xl">{course?.title}</h1>
            <div className="mt-1 flex flex-wrap items-center text-sm text-slate-500">
              <span>
                {course?.progress?.completed_content_count}/{course?.progress?.total_content_count} completed
              </span>
              <span className="mx-2 hidden sm:inline">&bull;</span>
              <span>{course?.progress?.percentage}% complete</span>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="hidden items-center gap-3 rounded-xl border border-slate-200 bg-white px-3 py-2 md:flex">
            <CompletionRing value={course?.progress?.percentage || 0} size={44} stroke={5} tone="emerald" />
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Completion</p>
              <p className="text-sm font-semibold text-slate-900">{Math.round(course?.progress?.percentage || 0)}%</p>
            </div>
          </div>

          <button
            onClick={() => setSidebarOpen((open) => !open)}
            className="lg:hidden p-2 text-slate-500 hover:text-slate-700 hover:bg-slate-100 rounded-lg"
            aria-label="Toggle course rail"
          >
            <Bars3BottomLeftIcon className="h-5 w-5" />
          </button>
        </div>
      </div>

      {/* ── Split pane ─────────────────────────────────────────────────────── */}
      <div className="relative mt-4 flex min-h-0 flex-1 overflow-hidden rounded-2xl border border-slate-200 bg-white">
        {/* ── Left sidebar ───────────────────────────────────────────────── */}
        <aside
          className={cn(
            'absolute inset-y-0 left-0 z-20 w-[88vw] border-r border-slate-200 bg-slate-50 transition-transform sm:w-96 lg:static lg:w-[24rem] lg:translate-x-0',
            sidebarOpen ? 'translate-x-0' : '-translate-x-full',
          )}
        >
          <div className="flex h-full flex-col">
            <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
              <h2 className="text-[15px] font-semibold text-indigo-600 truncate">{course?.title}</h2>
              <button
                type="button"
                onClick={() => setSidebarOpen(false)}
                className="rounded-md p-1 text-slate-500 hover:bg-slate-200 lg:hidden"
                aria-label="Close course rail"
              >
                <XMarkIcon className="h-5 w-5" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-3">
              {course?.modules.map((module) => {
                const isExpanded = expandedModules.includes(module.id);
                return (
                  <div key={module.id} className="mb-2 rounded-lg border border-slate-200 bg-white">
                    <button
                      type="button"
                      onClick={() => toggleModule(module.id)}
                      className={cn(
                        'w-full px-3 py-3 text-left',
                        module.is_locked ? 'bg-slate-100' : 'hover:bg-slate-50',
                      )}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                            Module {module.order}
                          </p>
                          <p className="text-[14px] font-semibold text-slate-900 leading-tight">{module.title}</p>
                          {module.is_locked && <p className="mt-1 text-xs text-slate-500">{module.lock_reason}</p>}
                        </div>
                        <div className="flex items-center gap-2">
                          <CompletionRing
                            value={module.completion_percentage}
                            size={26}
                            stroke={3}
                            tone={module.is_locked ? 'slate' : 'emerald'}
                          />
                          {isExpanded ? (
                            <ChevronDownIcon className="h-4 w-4 text-slate-500" />
                          ) : (
                            <ChevronRightIcon className="h-4 w-4 text-slate-500" />
                          )}
                        </div>
                      </div>
                    </button>

                    {isExpanded && (
                      <div className="border-t border-slate-200 bg-white">
                        {module.contents
                          .slice()
                          .sort((a, b) => a.order - b.order)
                          .map((content) => {
                            const isSelected = selectedContent?.id === content.id;
                            return (
                              <button
                                key={content.id}
                                type="button"
                                disabled={content.is_locked}
                                onClick={() => setSelectedContent(content)}
                                className={cn(
                                  'w-full border-l-4 px-3 py-2 text-left transition-colors',
                                  isSelected
                                    ? 'border-l-indigo-500 bg-indigo-50'
                                    : content.is_locked
                                    ? 'border-l-transparent bg-slate-50 text-slate-400 cursor-not-allowed'
                                    : 'border-l-transparent hover:bg-slate-50',
                                )}
                                title={content.is_locked ? content.lock_reason : undefined}
                              >
                                <div className="flex items-start gap-2">
                                  <span className="mt-0.5">
                                    {getContentIcon(content.content_type, !!content.is_completed, !!content.is_locked)}
                                  </span>
                                  <span className="min-w-0">
                                    <span
                                      className={cn(
                                        'block text-[13px] font-medium leading-tight',
                                        isSelected
                                          ? 'text-indigo-600'
                                          : content.is_locked
                                          ? 'text-slate-400'
                                          : 'text-slate-900',
                                      )}
                                    >
                                      {content.title}
                                    </span>
                                    <span className="mt-0.5 block text-[11px] text-slate-500">
                                      {contentTypeLabel(content.content_type)}
                                      {formatDuration(content.duration) ? ` \u2022 ${formatDuration(content.duration)}` : ''}
                                    </span>
                                  </span>
                                </div>
                              </button>
                            );
                          })}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </aside>

        {/* Backdrop overlay on mobile */}
        {sidebarOpen && (
          <div className="absolute inset-0 z-10 bg-black/20 lg:hidden" onClick={() => setSidebarOpen(false)} />
        )}

        {/* ── Right main area: content player ────────────────────────────── */}
        <main className="relative flex-1 overflow-y-auto bg-slate-50 p-3 sm:p-4 lg:p-6">
          {selectedContent ? (
              <ContentPlayer
                content={{
                  id: selectedContent.id,
                  title: selectedContent.title,
                  content_type: selectedContent.content_type,
                  file_url: selectedContent.file_url,
                  hls_url: selectedContent.hls_url,
                  thumbnail_url: selectedContent.thumbnail_url,
                  text_content: selectedContent.text_content,
                  duration: selectedContent.duration ?? undefined,
                  has_transcript: selectedContent.has_transcript,
                  transcript_vtt_url: selectedContent.transcript_vtt_url,
                }}
                initialProgress={selectedContent.video_progress_seconds}
                isCompleted={selectedContent.is_completed}
                onProgressUpdate={handleProgressUpdate}
                onComplete={handleComplete}
                onNextItem={nextUnlockedContent ? handleNextItem : undefined}
                nextItemLabel={nextUnlockedContent ? 'Go to next item' : undefined}
              />
          ) : (
            <div className="flex h-full items-center justify-center text-slate-500">
              Select an item to begin.
            </div>
          )}
        </main>
      </div>

      {/* ── AI Chat Widget ─────────────────────────────────────────────────── */}
      {courseId && <ChatWidget courseId={courseId} contentContext={chatContentContext} />}
    </div>
  );
};
