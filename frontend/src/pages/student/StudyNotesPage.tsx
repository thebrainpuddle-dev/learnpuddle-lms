// src/pages/student/StudyNotesPage.tsx
//
// Read-only course content browser — shows DOCUMENT and TEXT items
// from all assigned courses, grouped by course → module.

import React, { useEffect, useMemo, useState } from 'react';
import { FileText, Search, Download, ExternalLink, ChevronDown, ChevronRight, BookOpen } from 'lucide-react';
import { usePageTitle } from '../../hooks/usePageTitle';
import { studentService, type StudentCourseListItem, type StudentCourseDetail } from '../../services/studentService';

// ─── Types ───────────────────────────────────────────────────────────────────

interface NoteItem {
  id: string;
  title: string;
  content_type: 'DOCUMENT' | 'TEXT';
  file_url?: string;
  text_content?: string;
  moduleName: string;
  moduleId: string;
}

interface CourseNotes {
  courseId: string;
  courseTitle: string;
  items: NoteItem[];
}

// ─── Component ───────────────────────────────────────────────────────────────

export function StudyNotesPage() {
  usePageTitle('Study Notes');

  const [courses, setCourses] = useState<StudentCourseListItem[]>([]);
  const [courseDetails, setCourseDetails] = useState<Map<string, StudentCourseDetail>>(new Map());
  const [isLoading, setIsLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [expandedCourses, setExpandedCourses] = useState<Set<string>>(new Set());

  const [loadingCourses, setLoadingCourses] = useState<Set<string>>(new Set());

  // Fetch only the course list on mount
  useEffect(() => {
    let cancelled = false;

    async function load() {
      setIsLoading(true);
      try {
        const list = await studentService.getStudentCourses();
        if (cancelled) return;
        setCourses(list);
      } catch {
        // silent — empty state shown
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, []);

  // Build grouped notes from course details — includes all enrolled courses
  // so un-fetched ones still appear as expandable accordion items.
  const courseNotes: CourseNotes[] = useMemo(() => {
    const result: CourseNotes[] = [];

    for (const course of courses) {
      const detail = courseDetails.get(course.id);

      if (!detail) {
        // Detail not yet fetched — show the course with an empty item list
        result.push({ courseId: course.id, courseTitle: course.title, items: [] });
        continue;
      }

      const items: NoteItem[] = [];
      for (const mod of detail.modules) {
        for (const ct of mod.contents) {
          if (ct.content_type === 'DOCUMENT' || ct.content_type === 'TEXT') {
            items.push({
              id: ct.id,
              title: ct.title,
              content_type: ct.content_type as 'DOCUMENT' | 'TEXT',
              file_url: ct.file_url,
              text_content: ct.text_content,
              moduleName: mod.title,
              moduleId: mod.id,
            });
          }
        }
      }

      result.push({ courseId: course.id, courseTitle: course.title, items });
    }

    return result;
  }, [courses, courseDetails]);

  // Filter by search — when searching, only include courses with matching items
  const filtered = useMemo(() => {
    if (!search.trim()) return courseNotes;
    const q = search.toLowerCase();
    return courseNotes
      .map((cn) => ({
        ...cn,
        items: cn.items.filter(
          (it) =>
            it.title.toLowerCase().includes(q) ||
            cn.courseTitle.toLowerCase().includes(q) ||
            it.moduleName.toLowerCase().includes(q),
        ),
      }))
      .filter((cn) => cn.items.length > 0 || cn.courseTitle.toLowerCase().includes(q));
  }, [courseNotes, search]);

  const totalNotes = courseNotes.reduce((sum, cn) => sum + cn.items.length, 0);

  async function toggleCourse(courseId: string) {
    const isCurrentlyExpanded = expandedCourses.has(courseId);

    if (isCurrentlyExpanded) {
      // Collapse
      setExpandedCourses((prev) => {
        const next = new Set(prev);
        next.delete(courseId);
        return next;
      });
      return;
    }

    // Expand — fetch detail if not cached
    if (!courseDetails.has(courseId)) {
      setLoadingCourses((prev) => new Set(prev).add(courseId));
      try {
        const detail = await studentService.getStudentCourseDetail(courseId);
        setCourseDetails((prev) => {
          const next = new Map(prev);
          next.set(detail.id, detail);
          return next;
        });
      } catch {
        // Failed to load — don't expand
        setLoadingCourses((prev) => {
          const next = new Set(prev);
          next.delete(courseId);
          return next;
        });
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

  // ─── Loading ─────────────────────────────────────────────────────────────

  if (isLoading) {
    return (
      <div className="flex justify-center py-16">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600" />
      </div>
    );
  }

  // ─── Render ──────────────────────────────────────────────────────────────

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Study Notes</h1>
        <p className="mt-1 text-sm text-gray-500">
          Documents and text materials from your courses
          {totalNotes > 0 && (
            <span className="ml-1 text-gray-400">
              ({totalNotes} item{totalNotes !== 1 ? 's' : ''})
            </span>
          )}
        </p>
      </div>

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by course, module, or content name..."
          className="w-full pl-9 pr-4 py-2.5 border border-gray-300 rounded-lg text-sm focus:ring-indigo-500 focus:border-indigo-500"
        />
      </div>

      {/* Empty state */}
      {filtered.length === 0 && (
        <div className="text-center py-16 bg-white rounded-xl border border-gray-200">
          <BookOpen className="mx-auto h-10 w-10 text-gray-300 mb-3" />
          <p className="text-sm font-medium text-gray-500">
            {search ? 'No materials match your search' : 'No study materials available yet'}
          </p>
          <p className="text-xs text-gray-400 mt-1">
            {search
              ? 'Try a different search term'
              : 'Documents and text content from your courses will appear here'}
          </p>
        </div>
      )}

      {/* Course groups */}
      <div className="space-y-3">
        {filtered.map((cn) => {
          const isExpanded = expandedCourses.has(cn.courseId);
          const isCourseLoading = loadingCourses.has(cn.courseId);

          return (
            <div key={cn.courseId} className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
              {/* Course header */}
              <button
                type="button"
                onClick={() => toggleCourse(cn.courseId)}
                className="w-full flex items-center justify-between px-5 py-3.5 hover:bg-gray-50 transition-colors"
              >
                <div className="flex items-center gap-3 min-w-0">
                  {isCourseLoading ? (
                    <div className="h-4 w-4 animate-spin rounded-full border-2 border-indigo-600 border-t-transparent flex-shrink-0" />
                  ) : isExpanded ? (
                    <ChevronDown className="h-4 w-4 text-gray-400 flex-shrink-0" />
                  ) : (
                    <ChevronRight className="h-4 w-4 text-gray-400 flex-shrink-0" />
                  )}
                  <span className="text-sm font-semibold text-gray-900 truncate">{cn.courseTitle}</span>
                </div>
                <span className="text-xs text-gray-400 flex-shrink-0 ml-3">
                  {cn.items.length} item{cn.items.length !== 1 ? 's' : ''}
                </span>
              </button>

              {/* Content items */}
              {isExpanded && (
                <div className="border-t border-gray-100 divide-y divide-gray-50">
                  {cn.items.map((item) => (
                    <div key={item.id} className="flex items-center gap-3 px-5 py-3 hover:bg-gray-50 transition-colors">
                      <div className={`h-8 w-8 rounded-lg flex items-center justify-center flex-shrink-0 ${
                        item.content_type === 'DOCUMENT'
                          ? 'bg-blue-50 text-blue-500'
                          : 'bg-emerald-50 text-emerald-500'
                      }`}>
                        <FileText className="h-4 w-4" />
                      </div>

                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-gray-900 truncate">{item.title}</p>
                        <p className="text-xs text-gray-400 truncate">{item.moduleName}</p>
                      </div>

                      <span className="text-[10px] font-medium uppercase tracking-wide text-gray-400 flex-shrink-0">
                        {item.content_type === 'DOCUMENT' ? 'DOC' : 'TXT'}
                      </span>

                      {item.content_type === 'DOCUMENT' && item.file_url && (
                        <a
                          href={item.file_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="p-1.5 rounded-md text-gray-400 hover:text-indigo-600 hover:bg-indigo-50 transition-colors"
                          title="Open document"
                        >
                          <ExternalLink className="h-4 w-4" />
                        </a>
                      )}

                      {item.content_type === 'DOCUMENT' && item.file_url && (
                        <a
                          href={item.file_url}
                          download
                          className="p-1.5 rounded-md text-gray-400 hover:text-indigo-600 hover:bg-indigo-50 transition-colors"
                          title="Download"
                        >
                          <Download className="h-4 w-4" />
                        </a>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
