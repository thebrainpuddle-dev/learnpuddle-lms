// src/pages/teacher/TeacherStudyNotesPage.tsx
//
// Two-panel layout: left panel is a course content browser (accordion),
// right panel shows the AI StudySummaryPanel for the selected content.
// Mirrors student StudyNotesPage but uses teacher APIs and orange accent.

import { useEffect, useMemo, useState } from 'react';
import {
  Search, BookOpen, FileText, Video, Type, ChevronDown, ChevronRight,
  Sparkles, Check,
} from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import api from '../../config/api';
import { StudySummaryPanel } from '../../components/student/StudySummaryPanel';
import { usePageTitle } from '../../hooks/usePageTitle';
import { cn } from '../../design-system/theme/cn';
import type { StudySummaryListItem } from '../../types/studySummary';

// ─── Types ───────────────────────────────────────────────────────────────────

interface TeacherCourse {
  id: string;
  title: string;
  slug?: string;
  description?: string;
  is_published?: boolean;
  modules?: TeacherModule[];
}

interface TeacherModule {
  id: string;
  title: string;
  order: number;
  contents: TeacherContent[];
}

interface TeacherContent {
  id: string;
  title: string;
  content_type: 'VIDEO' | 'DOCUMENT' | 'LINK' | 'TEXT' | 'AI_CLASSROOM' | 'CHATBOT';
  has_transcript?: boolean;
  order: number;
}

interface ContentItem {
  id: string;
  title: string;
  content_type: 'VIDEO' | 'DOCUMENT' | 'TEXT';
  has_transcript?: boolean;
  moduleTitle: string;
}

interface SelectedContent {
  id: string;
  title: string;
  content_type: string;
}

const CONTENT_ICONS: Record<string, React.ElementType> = {
  VIDEO: Video,
  DOCUMENT: FileText,
  TEXT: Type,
};

const CONTENT_COLORS: Record<string, string> = {
  VIDEO: 'bg-purple-50 text-purple-500',
  DOCUMENT: 'bg-blue-50 text-blue-500',
  TEXT: 'bg-emerald-50 text-emerald-500',
};

// ─── Helpers ─────────────────────────────────────────────────────────────────

function isSummarizable(ct: { content_type: string; has_transcript?: boolean }): boolean {
  if (ct.content_type === 'DOCUMENT' || ct.content_type === 'TEXT') return true;
  if (ct.content_type === 'VIDEO' && ct.has_transcript) return true;
  return false;
}

// ─── Component ───────────────────────────────────────────────────────────────

export function TeacherStudyNotesPage() {
  usePageTitle('AI Study Notes');

  const [search, setSearch] = useState('');
  const [expandedCourses, setExpandedCourses] = useState<Set<string>>(new Set());
  const [courseDetails, setCourseDetails] = useState<Map<string, TeacherCourse>>(new Map());
  const [loadingCourses, setLoadingCourses] = useState<Set<string>>(new Set());
  const [selectedContent, setSelectedContent] = useState<SelectedContent | null>(null);
  const [summaryExistsMap, setSummaryExistsMap] = useState<Set<string>>(new Set());
  const [isMobileBrowserOpen, setIsMobileBrowserOpen] = useState(true);

  // Fetch course list
  const { data: courses = [], isLoading } = useQuery({
    queryKey: ['teacher', 'courses'],
    queryFn: async () => {
      const res = await api.get('/v1/teacher/courses/');
      return res.data as TeacherCourse[];
    },
  });

  // Fetch summary list to know which content has summaries
  const { data: summaries = [] } = useQuery({
    queryKey: ['teacher', 'study-summaries'],
    queryFn: async () => {
      const res = await api.get('/v1/teacher/study-summaries/');
      return res.data as StudySummaryListItem[];
    },
  });

  useEffect(() => {
    const readyIds = new Set(
      summaries
        .filter((s) => s.status === 'READY')
        .map((s) => s.content_id),
    );
    setSummaryExistsMap(readyIds);
  }, [summaries]);

  // Build course items grouped by course
  const courseItems = useMemo(() => {
    const result: Array<{
      courseId: string;
      courseTitle: string;
      items: ContentItem[];
    }> = [];

    for (const course of courses) {
      const detail = courseDetails.get(course.id);
      const items: ContentItem[] = [];

      if (detail?.modules) {
        for (const mod of detail.modules) {
          for (const ct of mod.contents) {
            if (isSummarizable(ct)) {
              items.push({
                id: ct.id,
                title: ct.title,
                content_type: ct.content_type as 'VIDEO' | 'DOCUMENT' | 'TEXT',
                has_transcript: ct.has_transcript,
                moduleTitle: mod.title,
              });
            }
          }
        }
      }

      result.push({ courseId: course.id, courseTitle: course.title, items });
    }

    return result;
  }, [courses, courseDetails]);

  // Filter by search
  const filtered = useMemo(() => {
    if (!search.trim()) return courseItems;
    const q = search.toLowerCase();
    return courseItems
      .map((c) => ({
        ...c,
        items: c.items.filter(
          (it) =>
            it.title.toLowerCase().includes(q) ||
            c.courseTitle.toLowerCase().includes(q) ||
            it.moduleTitle.toLowerCase().includes(q),
        ),
      }))
      .filter((c) => c.items.length > 0 || c.courseTitle.toLowerCase().includes(q));
  }, [courseItems, search]);

  // Toggle course expansion and lazy-load details
  async function toggleCourse(courseId: string) {
    if (expandedCourses.has(courseId)) {
      setExpandedCourses((prev) => {
        const next = new Set(prev);
        next.delete(courseId);
        return next;
      });
      return;
    }

    if (!courseDetails.has(courseId)) {
      setLoadingCourses((prev) => new Set(prev).add(courseId));
      try {
        const res = await api.get(`/v1/teacher/courses/${courseId}/`);
        const detail = res.data as TeacherCourse;
        setCourseDetails((prev) => {
          const next = new Map(prev);
          next.set(detail.id, detail);
          return next;
        });
      } catch {
        return;
      } finally {
        setLoadingCourses((prev) => {
          const next = new Set(prev);
          next.delete(courseId);
          return next;
        });
      }
    }

    setExpandedCourses((prev) => new Set(prev).add(courseId));
  }

  function selectContent(item: ContentItem) {
    setSelectedContent({
      id: item.id,
      title: item.title,
      content_type: item.content_type,
    });
    // On mobile, collapse the browser
    setIsMobileBrowserOpen(false);
  }

  // ─── Loading ─────────────────────────────────────────────────────────────

  if (isLoading) {
    return (
      <div className="flex justify-center py-16" role="status" aria-label="Loading">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-orange-600" />
        <span className="sr-only">Loading...</span>
      </div>
    );
  }

  // ─── Render ──────────────────────────────────────────────────────────────

  return (
    <div className="space-y-5">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">AI Study Notes</h1>
        <p className="mt-1 text-sm text-gray-500">
          Generate AI-powered summaries, flashcards, mind maps, and quiz prep from your course materials
        </p>
      </div>

      {/* Two-panel layout */}
      <div className="flex flex-col lg:flex-row gap-5 min-h-[60vh]">
        {/* Left Panel — Content Browser */}
        <div
          className={cn(
            'lg:w-[40%] flex-shrink-0',
            // On mobile, toggling browser visibility
            !isMobileBrowserOpen && selectedContent && 'hidden lg:block',
          )}
        >
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
            {/* Search */}
            <div className="p-3 border-b border-gray-100">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
                <input
                  type="text"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search courses and content..."
                  className="w-full pl-9 pr-4 py-2 border border-gray-200 rounded-lg text-sm focus:ring-orange-500 focus:border-orange-500"
                />
              </div>
            </div>

            {/* Course accordion */}
            <div className="max-h-[calc(60vh-60px)] overflow-y-auto">
              {filtered.length === 0 && (
                <div className="text-center py-12 px-4">
                  <BookOpen className="mx-auto h-8 w-8 text-gray-300 mb-2" />
                  <p className="text-sm text-gray-500">
                    {search ? 'No matching content found' : 'No courses available'}
                  </p>
                </div>
              )}

              {filtered.map((course) => {
                const isExpanded = expandedCourses.has(course.courseId);
                const isCourseLoading = loadingCourses.has(course.courseId);

                return (
                  <div key={course.courseId} className="border-b border-gray-100 last:border-0">
                    {/* Course header */}
                    <button
                      type="button"
                      onClick={() => toggleCourse(course.courseId)}
                      className="w-full flex items-center justify-between px-4 py-3 hover:bg-gray-50 transition-colors"
                    >
                      <div className="flex items-center gap-2.5 min-w-0">
                        {isCourseLoading ? (
                          <div className="h-4 w-4 animate-spin rounded-full border-2 border-orange-600 border-t-transparent flex-shrink-0" />
                        ) : isExpanded ? (
                          <ChevronDown className="h-4 w-4 text-gray-400 flex-shrink-0" />
                        ) : (
                          <ChevronRight className="h-4 w-4 text-gray-400 flex-shrink-0" />
                        )}
                        <span className="text-sm font-semibold text-gray-900 truncate">
                          {course.courseTitle}
                        </span>
                      </div>
                      {course.items.length > 0 && (
                        <span className="text-xs text-gray-400 flex-shrink-0 ml-2">
                          {course.items.length}
                        </span>
                      )}
                    </button>

                    {/* Content items */}
                    {isExpanded && (
                      <div className="bg-gray-50/50">
                        {course.items.length === 0 && (
                          <p className="px-4 py-3 text-xs text-gray-400 italic">
                            No summarizable content in this course
                          </p>
                        )}
                        {course.items.map((item) => {
                          const Icon = CONTENT_ICONS[item.content_type] || FileText;
                          const colorClass = CONTENT_COLORS[item.content_type] || 'bg-gray-50 text-gray-500';
                          const isSelected = selectedContent?.id === item.id;
                          const hasSummary = summaryExistsMap.has(item.id);

                          return (
                            <button
                              key={item.id}
                              type="button"
                              onClick={() => selectContent(item)}
                              className={cn(
                                'w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors',
                                isSelected
                                  ? 'bg-orange-50 border-l-2 border-orange-600'
                                  : 'hover:bg-gray-100 border-l-2 border-transparent',
                              )}
                            >
                              <div className={cn('h-7 w-7 rounded-md flex items-center justify-center flex-shrink-0', colorClass)}>
                                <Icon className="h-3.5 w-3.5" />
                              </div>
                              <div className="flex-1 min-w-0">
                                <p className={cn(
                                  'text-sm truncate',
                                  isSelected ? 'font-medium text-orange-700' : 'text-gray-700',
                                )}>
                                  {item.title}
                                </p>
                                <p className="text-[11px] text-gray-400 truncate">{item.moduleTitle}</p>
                              </div>
                              {hasSummary && (
                                <div className="h-5 w-5 rounded-full bg-emerald-100 flex items-center justify-center flex-shrink-0" title="Summary available">
                                  <Check className="h-3 w-3 text-emerald-600" />
                                </div>
                              )}
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
        </div>

        {/* Right Panel — Summary */}
        <div
          className={cn(
            'flex-1 min-w-0',
            // On mobile, show back button when panel is visible
            isMobileBrowserOpen && selectedContent && 'hidden lg:block',
          )}
        >
          {/* Mobile back button */}
          {selectedContent && (
            <button
              onClick={() => setIsMobileBrowserOpen(true)}
              className="lg:hidden flex items-center gap-1.5 text-sm text-orange-600 font-medium mb-3"
            >
              <ChevronRight className="h-4 w-4 rotate-180" />
              Back to content list
            </button>
          )}

          {selectedContent ? (
            <div className="animate-in slide-in-from-right-4 duration-300">
              <StudySummaryPanel
                contentId={selectedContent.id}
                contentTitle={selectedContent.title}
                contentType={selectedContent.content_type}
                mode="teacher"
                onClose={() => {
                  setSelectedContent(null);
                  setIsMobileBrowserOpen(true);
                }}
              />
            </div>
          ) : (
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm flex items-center justify-center min-h-[400px]">
              <div className="text-center px-6">
                <div className="h-14 w-14 rounded-xl bg-orange-50 flex items-center justify-center mx-auto mb-4">
                  <Sparkles className="h-7 w-7 text-orange-400" />
                </div>
                <p className="text-sm font-medium text-gray-700 mb-1">
                  Select a content item
                </p>
                <p className="text-xs text-gray-400 max-w-xs">
                  Choose a video, document, or text from the left panel to generate AI study materials
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
