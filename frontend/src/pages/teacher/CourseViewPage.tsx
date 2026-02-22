// src/pages/teacher/CourseViewPage.tsx

import React, { useState, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import DOMPurify from 'dompurify';
import { ContentPlayer } from '../../components/teacher';
import { CompletionRing } from '../../components/teacher/dashboard/CompletionRing';
import { ConfettiBurst } from '../../components/teacher/dashboard/ConfettiBurst';
import { teacherService } from '../../services/teacherService';
import type { TeacherCourseDetail } from '../../services/teacherService';
// Types extended in ../../types/index.ts (ContentWithProgress, Assignment, etc.)
import {
  ArrowLeftIcon,
  PlayCircleIcon,
  DocumentTextIcon,
  LinkIcon,
  Bars3BottomLeftIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  ClockIcon,
  LockClosedIcon,
  TrophyIcon,
} from '@heroicons/react/24/outline';
import { useTenantStore } from '../../stores/tenantStore';
import api from '../../config/api';
import { CheckCircleIcon as CheckCircleSolidIcon } from '@heroicons/react/24/solid';
import { usePageTitle } from '../../hooks/usePageTitle';

type ContentItem = TeacherCourseDetail['modules'][number]['contents'][number];

export const CourseViewPage: React.FC = () => {
  usePageTitle('Course');
  const { courseId } = useParams<{ courseId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { hasFeature } = useTenantStore();
  const [expandedModules, setExpandedModules] = useState<string[]>([]);
  const [selectedContent, setSelectedContent] = useState<ContentItem | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [showConfetti, setShowConfetti] = useState(false);
  
  // Throttle video progress updates (save every 5 seconds)
  const lastSavedRef = useRef<number>(0);
  const completionCelebratedRef = useRef(false);
  
  const handleProgressUpdate = useCallback(async (seconds: number) => {
    if (!selectedContent || selectedContent.content_type !== 'VIDEO') return;
    if (seconds - lastSavedRef.current >= 5) {
      lastSavedRef.current = seconds;
      try {
        await teacherService.updateContent(selectedContent.id, { 
          video_progress_seconds: seconds 
        });
        // Invalidate queries to refresh progress on dashboard/courses pages
        queryClient.invalidateQueries({ queryKey: ['teacherDashboard'] });
        queryClient.invalidateQueries({ queryKey: ['teacherCourses'] });
      } catch {
        // Silent fail - don't interrupt playback
      }
    }
  }, [selectedContent, queryClient]);
  
  // Reset lastSavedRef when content changes
  React.useEffect(() => {
    lastSavedRef.current = 0;
  }, [selectedContent?.id]);
  
  // Fetch course details
  const { data: course, isLoading } = useQuery<TeacherCourseDetail>({
    queryKey: ['course', courseId],
    enabled: Boolean(courseId),
    queryFn: () => teacherService.getCourse(courseId as string),
  });
  const selectedModule = React.useMemo(() => {
    if (!course || !selectedContent) return null;
    return course.modules.find((module) => module.contents.some((item) => item.id === selectedContent.id)) || null;
  }, [course, selectedContent]);
  
  // Initialize expanded modules and selected content
  React.useEffect(() => {
    if (course?.modules) {
      const unlockedModules = course.modules.filter((module) => !module.is_locked);
      const firstTargetModule =
        unlockedModules.find((module) => !module.is_completed) ||
        unlockedModules[0] ||
        course.modules[0];

      if (firstTargetModule) {
        setExpandedModules([firstTargetModule.id]);
        const firstIncompleteUnlockedContent = firstTargetModule.contents.find(
          (item) => !item.is_locked && !item.is_completed,
        );
        const firstUnlockedContent = firstTargetModule.contents.find((item) => !item.is_locked);
        setSelectedContent((current) => {
          if (
            current &&
            !current.is_locked &&
            course.modules.some((module) => module.contents.some((item) => item.id === current.id))
          ) {
            return current;
          }
          return firstIncompleteUnlockedContent || firstUnlockedContent || firstTargetModule.contents[0] || null;
        });
      }
    }
  }, [course]);

  React.useEffect(() => {
    if ((course?.progress?.percentage || 0) < 100 || completionCelebratedRef.current) return;
    completionCelebratedRef.current = true;
    setShowConfetti(true);
    window.setTimeout(() => setShowConfetti(false), 1700);
  }, [course?.progress?.percentage]);
  
  const toggleModule = (moduleId: string) => {
    setExpandedModules(prev => 
      prev.includes(moduleId) 
        ? prev.filter(id => id !== moduleId)
        : [...prev, moduleId]
    );
  };
  
  const getContentIcon = (type: string, isCompleted: boolean, isLocked: boolean) => {
    if (isLocked) {
      return <LockClosedIcon className="h-5 w-5 text-slate-400" />;
    }
    if (isCompleted) {
      return <CheckCircleSolidIcon className="h-5 w-5 text-emerald-500" />;
    }
    switch (type) {
      case 'VIDEO':
        return <PlayCircleIcon className="h-5 w-5 text-gray-400" />;
      case 'DOCUMENT':
        return <DocumentTextIcon className="h-5 w-5 text-gray-400" />;
      case 'LINK':
        return <LinkIcon className="h-5 w-5 text-gray-400" />;
      default:
        return <Bars3BottomLeftIcon className="h-5 w-5 text-gray-400" />;
    }
  };
  
  const formatDuration = (seconds?: number) => {
    if (!seconds) return '';
    const mins = Math.floor(seconds / 60);
    return `${mins} min`;
  };
  
  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-emerald-600"></div>
      </div>
    );
  }
  
  return (
    <div className="flex flex-col h-[calc(100vh-8rem)]">
      <ConfettiBurst active={showConfetti} />
      {/* Header */}
      <div className="flex items-center justify-between pb-4 border-b border-gray-200">
        <div className="flex items-center">
          <button
            onClick={() => navigate('/teacher/courses')}
            className="mr-4 p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg"
          >
            <ArrowLeftIcon className="h-5 w-5" />
          </button>
          <div>
            <h1 className="text-xl font-bold text-gray-900">{course?.title}</h1>
            <div className="flex items-center text-sm text-gray-500 mt-1">
              <span>{course?.progress?.completed_content_count}/{course?.progress?.total_content_count} completed</span>
              <span className="mx-2">•</span>
              <span>{course?.progress?.percentage}% complete</span>
            </div>
          </div>
        </div>
        <div className="hidden items-center gap-3 rounded-xl border border-slate-200 bg-white px-3 py-2 lg:flex">
          <CompletionRing
            value={course?.progress?.percentage || 0}
            size={46}
            stroke={5}
            tone="emerald"
          />
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Course Completion</p>
            <p className="text-sm font-semibold text-slate-900">{Math.round(course?.progress?.percentage || 0)}%</p>
          </div>
        </div>
        
        <div className="flex items-center gap-2">
          {hasFeature('certificates') && course?.progress?.percentage === 100 && (
            <button
              onClick={async () => {
                try {
                  const res = await api.get(`/teacher/courses/${courseId}/certificate/`);
                  const d = res.data;
                  const w = window.open('', '_blank');
                  if (w) {
                    const doc = w.document;
                    doc.open();
                    doc.write('<html><head><title>Certificate</title><style>body{font-family:Georgia,serif;text-align:center;padding:60px;border:8px double #1F4788;margin:40px}h1{color:#1F4788;font-size:36px}h2{font-size:24px;color:#333}p{font-size:18px;color:#666}.id{font-size:12px;color:#999;margin-top:40px}</style></head><body><div id="cert"></div></body></html>');
                    doc.close();
                    const container = doc.getElementById('cert');
                    if (container) {
                      const h1 = doc.createElement('h1'); h1.textContent = 'Certificate of Completion'; container.appendChild(h1);
                      const p1 = doc.createElement('p'); p1.textContent = 'This certifies that'; container.appendChild(p1);
                      const h2a = doc.createElement('h2'); h2a.textContent = d.teacher_name || ''; container.appendChild(h2a);
                      const p2 = doc.createElement('p'); p2.textContent = 'has successfully completed'; container.appendChild(p2);
                      const h2b = doc.createElement('h2'); h2b.textContent = d.course_title || ''; container.appendChild(h2b);
                      const escMap: Record<string, string> = {'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;',"'":'&#39;'};
                      const p3 = doc.createElement('p'); p3.innerHTML = 'at <strong>' + (d.school_name || '').replace(/[<>&"']/g, (ch: string) => escMap[ch] || ch) + '</strong>'; container.appendChild(p3);
                      const p4 = doc.createElement('p'); p4.textContent = 'Completed on: ' + (d.completed_at ? new Date(d.completed_at).toLocaleDateString() : 'N/A'); container.appendChild(p4);
                      const pId = doc.createElement('p'); pId.className = 'id'; pId.textContent = 'ID: ' + (d.certificate_id || ''); container.appendChild(pId);
                    }
                    w.print();
                  }
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
        </div>

        <button
          onClick={() => setSidebarOpen(!sidebarOpen)}
          className="lg:hidden p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg"
        >
          <Bars3BottomLeftIcon className="h-5 w-5" />
        </button>
      </div>
      
      {/* Main content area */}
      <div className="flex flex-1 overflow-hidden mt-4">
        {/* Content player */}
        <div data-tour="teacher-course-player" className={`flex-1 overflow-y-auto pr-4 ${sidebarOpen ? 'lg:mr-80' : ''}`}>
          {selectedModule?.description && (
            <div className="mb-4 rounded-xl border border-gray-200 bg-white p-4">
              <h2 className="mb-2 text-sm font-semibold text-gray-900">Module Overview</h2>
              <div
                className="prose prose-sm max-w-none text-gray-700"
                dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(selectedModule.description) }}
              />
            </div>
          )}
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
            />
          ) : (
            <div className="flex items-center justify-center h-full text-gray-500">
              Select a lesson to begin
            </div>
          )}
        </div>
        
        {/* Sidebar - Module list */}
        <div data-tour="teacher-course-structure" className={`fixed right-0 top-0 bottom-0 w-80 bg-white border-l border-gray-200 overflow-y-auto transform transition-transform lg:translate-x-0 lg:static lg:right-auto lg:top-auto lg:bottom-auto ${
          sidebarOpen ? 'translate-x-0' : 'translate-x-full'
        }`} style={{ marginTop: '64px', paddingTop: '24px' }}>
          <div className="p-4">
            <h2 className="font-semibold text-gray-900 mb-4">Course Content</h2>
            
            {/* Progress bar */}
            <div className="mb-4">
              <div className="flex justify-between text-xs text-gray-500 mb-1">
                <span>Progress</span>
                <span>{course?.progress?.percentage}%</span>
              </div>
              <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                <div 
                  className="h-full bg-emerald-500 rounded-full"
                  style={{ width: `${course?.progress?.percentage || 0}%` }}
                />
              </div>
            </div>
            
            {/* Modules */}
            <div className="space-y-2">
              {course?.modules.map((module) => {
                const isExpanded = expandedModules.includes(module.id);
                const completedCount = module.completed_content_count;
                const isModuleComplete = module.is_completed;
                
                return (
                  <div
                    key={module.id}
                    className={`border rounded-lg overflow-hidden ${
                      module.is_locked ? 'border-slate-200 bg-slate-50/70' : 'border-gray-200'
                    }`}
                  >
                    <button
                      onClick={() => toggleModule(module.id)}
                      className={`w-full flex items-center justify-between p-3 transition-colors ${
                        module.is_locked ? 'bg-slate-100' : 'bg-gray-50 hover:bg-gray-100'
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        <CompletionRing
                          value={module.completion_percentage}
                          size={28}
                          stroke={3}
                          label={`${Math.round(module.completion_percentage)}%`}
                          tone={module.is_locked ? 'slate' : 'emerald'}
                        />
                        {isModuleComplete ? (
                          <CheckCircleSolidIcon className="h-5 w-5 text-emerald-500 mr-2" />
                        ) : (
                          <div className="h-5 w-5 rounded-full border-2 border-gray-300 mr-2 flex items-center justify-center">
                            <span className="text-xs text-gray-500">{completedCount}</span>
                          </div>
                        )}
                        <div className="text-left">
                          <p className="font-medium text-sm text-gray-900">{module.title}</p>
                          {module.is_locked && (
                            <p className="text-xs text-slate-500">{module.lock_reason}</p>
                          )}
                        </div>
                        {module.is_locked && <LockClosedIcon className="h-4 w-4 text-slate-400" />}
                      </div>
                      {isExpanded ? (
                        <ChevronDownIcon className="h-4 w-4 text-gray-500" />
                      ) : (
                        <ChevronRightIcon className="h-4 w-4 text-gray-500" />
                      )}
                    </button>
                    
                    {isExpanded && (
                      <div className="border-t border-gray-200">
                        {module.description && (
                          <div className="border-b border-gray-100 bg-gray-50 px-3 py-2">
                            <div
                              className="prose prose-sm max-w-none text-gray-600"
                              dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(module.description) }}
                            />
                          </div>
                        )}
                        {module.contents.map((content) => (
                          <button
                            key={content.id}
                            type="button"
                            disabled={content.is_locked}
                            onClick={() => setSelectedContent(content)}
                            title={content.is_locked ? content.lock_reason : undefined}
                            className={`w-full flex items-center p-3 text-left transition-colors ${
                              selectedContent?.id === content.id
                                ? 'bg-emerald-50 border-l-2 border-emerald-500'
                                : content.is_locked
                                  ? 'bg-slate-50 text-slate-400 cursor-not-allowed'
                                  : 'hover:bg-gray-50'
                            }`}
                          >
                            {getContentIcon(content.content_type, !!content.is_completed, !!content.is_locked)}
                            <div className="ml-3 flex-1 min-w-0">
                              <p className={`text-sm truncate ${
                                selectedContent?.id === content.id
                                  ? 'text-emerald-700 font-medium'
                                  : content.is_locked
                                    ? 'text-slate-400'
                                    : 'text-gray-700'
                              }`}>
                                {content.title}
                              </p>
                              {content.duration && (
                                <p className="text-xs text-gray-400 flex items-center mt-0.5">
                                  <ClockIcon className="h-3 w-3 mr-1" />
                                  {formatDuration(content.duration)}
                                </p>
                              )}
                              {content.is_locked && (
                                <p className="mt-0.5 text-xs text-slate-400">{content.lock_reason}</p>
                              )}
                            </div>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
