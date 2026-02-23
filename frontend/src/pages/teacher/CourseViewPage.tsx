// src/pages/teacher/CourseViewPage.tsx

import React, { useState, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ContentPlayer } from '../../components/teacher';
import { CompletionRing } from '../../components/teacher/dashboard/CompletionRing';
import { ConfettiBurst } from '../../components/teacher/dashboard/ConfettiBurst';
import { teacherService } from '../../services/teacherService';
import type { TeacherAssignmentListItem, TeacherCourseDetail } from '../../services/teacherService';
import {
  ArrowLeftIcon,
  PlayCircleIcon,
  DocumentTextIcon,
  LinkIcon,
  Bars3BottomLeftIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  LockClosedIcon,
  TrophyIcon,
  ClipboardDocumentListIcon,
  XMarkIcon,
  HandThumbUpIcon,
  HandThumbDownIcon,
  FlagIcon,
} from '@heroicons/react/24/outline';
import { useTenantStore } from '../../stores/tenantStore';
import api from '../../config/api';
import { CheckCircleIcon as CheckCircleSolidIcon } from '@heroicons/react/24/solid';
import { usePageTitle } from '../../hooks/usePageTitle';

type ContentItem = TeacherCourseDetail['modules'][number]['contents'][number];

const contentTypeLabel = (type: ContentItem['content_type']) => {
  if (type === 'VIDEO') return 'Video';
  if (type === 'DOCUMENT') return 'Reading';
  if (type === 'LINK') return 'Link';
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
  const { hasFeature } = useTenantStore();

  const [expandedModules, setExpandedModules] = useState<string[]>([]);
  const [selectedContent, setSelectedContent] = useState<ContentItem | null>(null);
  const [selectedAssignment, setSelectedAssignment] = useState<TeacherAssignmentListItem | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(() =>
    typeof window !== 'undefined' && typeof window.matchMedia === 'function'
      ? window.matchMedia('(min-width: 1024px)').matches
      : true,
  );
  const [showConfetti, setShowConfetti] = useState(false);
  const [showHonorCodeModal, setShowHonorCodeModal] = useState(false);

  const lastSavedRef = useRef<number>(0);
  const completionCelebratedRef = useRef(false);

  const handleProgressUpdate = useCallback(
    async (seconds: number) => {
      if (!selectedContent || selectedContent.content_type !== 'VIDEO') return;
      if (seconds - lastSavedRef.current < 5) return;
      lastSavedRef.current = seconds;
      try {
        await teacherService.updateContent(selectedContent.id, { video_progress_seconds: seconds });
        queryClient.invalidateQueries({ queryKey: ['teacherDashboard'] });
        queryClient.invalidateQueries({ queryKey: ['teacherCourses'] });
      } catch {
        // Silent fail; progress will retry on next tick.
      }
    },
    [selectedContent, queryClient],
  );

  React.useEffect(() => {
    lastSavedRef.current = 0;
  }, [selectedContent?.id]);

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

  const { data: course, isLoading } = useQuery<TeacherCourseDetail>({
    queryKey: ['course', courseId],
    enabled: Boolean(courseId),
    queryFn: () => teacherService.getCourse(courseId as string),
  });

  const { data: courseAssignments = [] } = useQuery({
    queryKey: ['teacherAssignmentsForCourse', courseId],
    enabled: Boolean(courseId),
    queryFn: async () => {
      const assignments = await teacherService.listAssignments();
      return assignments
        .filter((assignment) => assignment.course_id === courseId)
        .sort((a, b) => a.title.localeCompare(b.title));
    },
  });

  React.useEffect(() => {
    if ((course?.progress?.percentage || 0) < 100 || completionCelebratedRef.current) return;
    completionCelebratedRef.current = true;
    setShowConfetti(true);
    window.setTimeout(() => setShowConfetti(false), 1700);
  }, [course?.progress?.percentage]);

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

  const nextPendingAssignment = React.useMemo(
    () => courseAssignments.find((assignment) => assignment.submission_status === 'PENDING') || null,
    [courseAssignments],
  );

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

  const handleOpenAssignment = (assignment: TeacherAssignmentListItem) => {
    setSelectedContent(null);
    setSelectedAssignment(assignment);
    setShowHonorCodeModal(true);
  };

  const handleContinueAssignment = () => {
    if (!selectedAssignment) return;
    setShowHonorCodeModal(false);
    if (selectedAssignment.is_quiz) {
      navigate(`/teacher/quizzes/${selectedAssignment.id}`);
      return;
    }
    navigate('/teacher/assignments');
  };

  const handleNextItem = () => {
    if (nextUnlockedContent) {
      setSelectedAssignment(null);
      setSelectedContent(nextUnlockedContent);
      setExpandedModules((prev) =>
        prev.includes(nextUnlockedContent.moduleId) ? prev : [...prev, nextUnlockedContent.moduleId],
      );
      return;
    }
    if (nextPendingAssignment) {
      handleOpenAssignment(nextPendingAssignment);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="flex h-[calc(100dvh-6.5rem)] flex-col lg:h-[calc(100vh-8rem)]">
      <ConfettiBurst active={showConfetti} />

      <div className="flex flex-col gap-3 border-b border-gray-200 pb-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-center">
          <button
            onClick={() => navigate('/teacher/courses')}
            className="mr-3 p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg"
            aria-label="Back to my courses"
          >
            <ArrowLeftIcon className="h-5 w-5" />
          </button>
          <div className="min-w-0">
            <h1 className="truncate text-lg font-semibold text-gray-900 sm:text-xl">{course?.title}</h1>
            <div className="mt-1 flex flex-wrap items-center text-sm text-gray-500">
              <span>
                {course?.progress?.completed_content_count}/{course?.progress?.total_content_count} completed
              </span>
              <span className="mx-2 hidden sm:inline">•</span>
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

          {hasFeature('certificates') && course?.progress?.percentage === 100 && (
            <button
              onClick={async () => {
                try {
                  const res = await api.get(`/teacher/courses/${courseId}/certificate/`);
                  const d = res.data;
                  const w = window.open('', '_blank');
                  if (!w) return;
                  const doc = w.document;
                  doc.open();
                  doc.write(
                    '<html><head><title>Certificate</title><style>body{font-family:Georgia,serif;text-align:center;padding:60px;border:8px double #1F4788;margin:40px}h1{color:#1F4788;font-size:36px}h2{font-size:24px;color:#333}p{font-size:18px;color:#666}.id{font-size:12px;color:#999;margin-top:40px}</style></head><body><div id="cert"></div></body></html>',
                  );
                  doc.close();
                  const container = doc.getElementById('cert');
                  if (!container) return;
                  const h1 = doc.createElement('h1');
                  h1.textContent = 'Certificate of Completion';
                  container.appendChild(h1);
                  const p1 = doc.createElement('p');
                  p1.textContent = 'This certifies that';
                  container.appendChild(p1);
                  const h2a = doc.createElement('h2');
                  h2a.textContent = d.teacher_name || '';
                  container.appendChild(h2a);
                  const p2 = doc.createElement('p');
                  p2.textContent = 'has successfully completed';
                  container.appendChild(p2);
                  const h2b = doc.createElement('h2');
                  h2b.textContent = d.course_title || '';
                  container.appendChild(h2b);
                  const p3 = doc.createElement('p');
                  p3.textContent = `at ${d.school_name || ''}`;
                  container.appendChild(p3);
                  const p4 = doc.createElement('p');
                  p4.textContent = `Completed on: ${
                    d.completed_at ? new Date(d.completed_at).toLocaleDateString() : 'N/A'
                  }`;
                  container.appendChild(p4);
                  const pId = doc.createElement('p');
                  pId.className = 'id';
                  pId.textContent = `ID: ${d.certificate_id || ''}`;
                  container.appendChild(pId);
                  w.print();
                } catch {
                  alert('Could not generate certificate.');
                }
              }}
              className="inline-flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-amber-700 bg-amber-50 border border-amber-200 rounded-lg hover:bg-amber-100"
            >
              <TrophyIcon className="h-4 w-4" />
              Certificate
            </button>
          )}

          <button
            onClick={() => setSidebarOpen((open) => !open)}
            className="lg:hidden p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg"
            aria-label="Toggle course rail"
          >
            <Bars3BottomLeftIcon className="h-5 w-5" />
          </button>
        </div>
      </div>

      <div className="relative mt-4 flex min-h-0 flex-1 overflow-hidden rounded-2xl border border-slate-200 bg-white">
        <aside
          className={`absolute inset-y-0 left-0 z-20 w-[88vw] border-r border-slate-200 bg-slate-50 transition-transform sm:w-96 lg:static lg:w-[24rem] lg:translate-x-0 ${
            sidebarOpen ? 'translate-x-0' : '-translate-x-full'
          }`}
        >
          <div className="flex h-full flex-col">
            <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
              <h2 className="text-lg font-semibold text-blue-700 truncate">{course?.title}</h2>
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
                      className={`w-full px-3 py-3 text-left ${
                        module.is_locked ? 'bg-slate-100' : 'hover:bg-slate-50'
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                            Module {module.order}
                          </p>
                          <p className="text-base font-semibold text-slate-900 leading-tight">{module.title}</p>
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
                                onClick={() => {
                                  setSelectedAssignment(null);
                                  setSelectedContent(content);
                                }}
                                className={`w-full border-l-4 px-3 py-2 text-left transition-colors ${
                                  isSelected
                                    ? 'border-l-blue-600 bg-blue-50'
                                    : content.is_locked
                                    ? 'border-l-transparent bg-slate-50 text-slate-400 cursor-not-allowed'
                                    : 'border-l-transparent hover:bg-slate-50'
                                }`}
                                title={content.is_locked ? content.lock_reason : undefined}
                              >
                                <div className="flex items-start gap-2">
                                  <span className="mt-0.5">
                                    {getContentIcon(content.content_type, !!content.is_completed, !!content.is_locked)}
                                  </span>
                                  <span className="min-w-0">
                                    <span
                                      className={`block text-sm font-medium leading-tight ${
                                        isSelected ? 'text-blue-700' : content.is_locked ? 'text-slate-400' : 'text-slate-900'
                                      }`}
                                    >
                                      {content.title}
                                    </span>
                                    <span className="mt-0.5 block text-xs text-slate-500">
                                      {contentTypeLabel(content.content_type)}
                                      {formatDuration(content.duration) ? ` • ${formatDuration(content.duration)}` : ''}
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

              {courseAssignments.length > 0 && (
                <div className="mt-4 rounded-lg border border-slate-200 bg-white">
                  <div className="border-b border-slate-200 px-3 py-2">
                    <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Assignments</p>
                  </div>
                  {courseAssignments.map((assignment) => {
                    const isSelected = selectedAssignment?.id === assignment.id;
                    const isDone = assignment.submission_status !== 'PENDING';
                    return (
                      <button
                        key={assignment.id}
                        type="button"
                        onClick={() => handleOpenAssignment(assignment)}
                        className={`w-full border-l-4 px-3 py-2 text-left transition-colors ${
                          isSelected ? 'border-l-blue-600 bg-blue-50' : 'border-l-transparent hover:bg-slate-50'
                        }`}
                      >
                        <div className="flex items-start gap-2">
                          <span className="mt-0.5">
                            {isDone ? (
                              <CheckCircleSolidIcon className="h-4 w-4 text-emerald-500" />
                            ) : (
                              <ClipboardDocumentListIcon className="h-4 w-4 text-slate-400" />
                            )}
                          </span>
                          <span className="min-w-0">
                            <span className={`block text-sm font-medium ${isSelected ? 'text-blue-700' : 'text-slate-900'}`}>
                              {assignment.title}
                            </span>
                            <span className="mt-0.5 block text-xs text-slate-500">
                              {assignment.is_quiz ? 'Graded Assignment' : 'Assignment'}
                            </span>
                          </span>
                        </div>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </aside>

        {sidebarOpen && <div className="absolute inset-0 z-10 bg-black/20 lg:hidden" onClick={() => setSidebarOpen(false)} />}

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
              onComplete={async () => {
                try {
                  await teacherService.completeContent(selectedContent.id);
                  await queryClient.invalidateQueries({ queryKey: ['course', courseId] });
                  await queryClient.invalidateQueries({ queryKey: ['teacherDashboard'] });
                  await queryClient.invalidateQueries({ queryKey: ['teacherCourses'] });
                } catch (error: any) {
                  const reason = error?.response?.data?.error || 'This lesson is locked.';
                  alert(reason);
                }
              }}
              onNextItem={nextUnlockedContent || nextPendingAssignment ? handleNextItem : undefined}
              nextItemLabel={nextUnlockedContent ? 'Go to next item' : nextPendingAssignment ? 'Go to assignment' : undefined}
            />
          ) : selectedAssignment ? (
            <div className="rounded-xl border border-slate-200 bg-white p-4 sm:p-6 lg:p-8">
              <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <h2 className="text-2xl font-semibold text-slate-900 sm:text-3xl">{selectedAssignment.title}</h2>
                  <p className="mt-3 max-w-3xl text-base text-slate-700 sm:mt-4 sm:text-lg">
                    {selectedAssignment.description || 'Complete the assignment to continue your learning path.'}
                  </p>
                </div>
                <ClipboardDocumentListIcon className="h-12 w-12 text-slate-300" />
              </div>
              <button
                type="button"
                onClick={() => setShowHonorCodeModal(true)}
                className="inline-flex w-full items-center justify-center rounded-lg bg-blue-600 px-6 py-3 text-base font-semibold text-white hover:bg-blue-700 sm:w-auto"
              >
                Open Assignment
              </button>

              <div className="mt-8 flex flex-wrap items-center gap-5 border-t border-slate-200 pt-5 text-blue-600 sm:mt-10 sm:gap-8">
                <button type="button" className="inline-flex items-center gap-2 text-sm font-semibold">
                  <HandThumbUpIcon className="h-5 w-5" />
                  Like
                </button>
                <button type="button" className="inline-flex items-center gap-2 text-sm font-semibold">
                  <HandThumbDownIcon className="h-5 w-5" />
                  Dislike
                </button>
                <button type="button" className="inline-flex items-center gap-2 text-sm font-semibold">
                  <FlagIcon className="h-5 w-5" />
                  Report an issue
                </button>
              </div>
            </div>
          ) : (
            <div className="flex h-full items-center justify-center text-slate-500">Select an item to begin.</div>
          )}
        </main>
      </div>

      {showHonorCodeModal && selectedAssignment && (
        <div className="fixed inset-0 z-40 flex items-end justify-center bg-black/40 p-2 sm:items-center sm:px-4">
          <div className="w-full max-w-2xl rounded-t-2xl bg-white p-4 shadow-2xl sm:rounded-2xl sm:p-8">
            <div className="mb-4 flex items-start justify-between">
              <h3 className="text-2xl font-semibold text-slate-900 sm:text-4xl">Coursera Honor Code</h3>
              <button
                type="button"
                onClick={() => setShowHonorCodeModal(false)}
                className="rounded-md p-1 text-slate-500 hover:bg-slate-100"
                aria-label="Close honor code"
              >
                <XMarkIcon className="h-6 w-6" />
              </button>
            </div>

            <p className="mb-4 text-lg text-slate-800 sm:text-2xl">We protect integrity in submitted work.</p>
            <p className="mb-3 text-base text-slate-700 sm:text-lg">Before continuing, agree to these principles:</p>
            <ul className="list-disc space-y-1 pl-6 text-base text-slate-700 sm:text-lg">
              <li>Submit your own original work.</li>
              <li>Avoid sharing answers with others.</li>
              <li>Report suspected violations.</li>
            </ul>

            <div className="mt-8 flex justify-end">
              <button
                type="button"
                onClick={handleContinueAssignment}
                className="w-full rounded-lg bg-blue-600 px-8 py-3 text-base font-semibold text-white hover:bg-blue-700 sm:w-auto"
              >
                Continue
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
