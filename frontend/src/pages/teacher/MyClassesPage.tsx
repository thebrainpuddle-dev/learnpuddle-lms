// src/pages/teacher/MyClassesPage.tsx
//
// Teacher "My Classes" page — shows all teaching assignments grouped by subject,
// with section cards in a responsive grid.  Uses lucide-react icons and the
// teacher design system (tp-accent orange, cn utility).

import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  BookOpen,
  Users,
  GraduationCap,
  ChevronRight,
  Layers,
  Star,
} from 'lucide-react';
import { cn } from '../../design-system/theme/cn';
import { usePageTitle } from '../../hooks/usePageTitle';
import {
  academicsService,
  type MyClassesResponse,
  type MyClassesAssignment,
} from '../../services/academicsService';

// ─── Skeleton Card ──────────────────────────────────────────────────────────

function SkeletonCard() {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 animate-pulse">
      <div className="flex items-start justify-between">
        <div className="space-y-2 flex-1">
          <div className="h-4 w-3/4 bg-gray-200 rounded" />
          <div className="h-3 w-1/2 bg-gray-100 rounded" />
        </div>
      </div>
      <div className="flex items-center gap-4 mt-5">
        <div className="h-3 w-20 bg-gray-100 rounded" />
        <div className="h-3 w-20 bg-gray-100 rounded" />
      </div>
    </div>
  );
}

// ─── Section Card ───────────────────────────────────────────────────────────

function SectionCard({
  section,
  onClick,
}: {
  section: MyClassesAssignment['sections'][number];
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'group relative bg-white rounded-xl border border-gray-200 p-5 text-left',
        'hover:border-primary-300 hover:shadow-md',
        'focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2',
        'transition-all duration-200',
      )}
    >
      {/* Class Teacher badge */}
      {section.is_class_teacher && (
        <span className="absolute top-3 right-3 inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-semibold rounded-full bg-amber-100 text-amber-700">
          <Star className="h-3 w-3" />
          Class Teacher
        </span>
      )}

      {/* Section name */}
      <div className="pr-20">
        <div className="font-semibold text-gray-900 text-base leading-tight">
          {section.grade_name} &middot; Section {section.name}
        </div>
        {section.grade_band_name && (
          <p className="text-xs text-gray-400 mt-0.5">
            {section.grade_band_name}
          </p>
        )}
      </div>

      {/* Stats row */}
      <div className="flex items-center gap-5 mt-4">
        <div className="flex items-center gap-1.5 text-sm text-gray-600">
          <Users className="h-4 w-4 text-gray-400" />
          <span>
            {section.student_count}{' '}
            {section.student_count === 1 ? 'student' : 'students'}
          </span>
        </div>
        <div className="flex items-center gap-1.5 text-sm text-gray-600">
          <BookOpen className="h-4 w-4 text-gray-400" />
          <span>
            {section.course_count}{' '}
            {section.course_count === 1 ? 'course' : 'courses'}
          </span>
        </div>
      </div>

      {/* Hover indicator */}
      <div className="flex items-center gap-1 mt-3 text-xs text-tp-accent opacity-0 group-hover:opacity-100 transition-opacity">
        View dashboard
        <ChevronRight className="h-3 w-3" />
      </div>
    </button>
  );
}

// ─── Subject Group ──────────────────────────────────────────────────────────

function SubjectGroup({
  assignment,
  onSectionClick,
}: {
  assignment: MyClassesAssignment;
  onSectionClick: (sectionId: string) => void;
}) {
  return (
    <section>
      {/* Subject header */}
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <BookOpen className="h-5 w-5 text-tp-accent" />
        <h2 className="text-lg font-semibold text-gray-900">
          {assignment.subject.name}
        </h2>
        <span className="px-2 py-0.5 text-xs rounded-full bg-gray-100 text-gray-600 font-mono">
          {assignment.subject.code}
        </span>
        {assignment.subject.department && (
          <span className="px-2 py-0.5 text-xs rounded-full bg-blue-50 text-blue-600">
            {assignment.subject.department}
          </span>
        )}
      </div>

      {/* Section cards grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {assignment.sections.map((section) => (
          <SectionCard
            key={section.id}
            section={section}
            onClick={() => onSectionClick(section.id)}
          />
        ))}
      </div>
    </section>
  );
}

// ─── Main Component ─────────────────────────────────────────────────────────

export const MyClassesPage: React.FC = () => {
  usePageTitle('My Classes');
  const navigate = useNavigate();

  const { data, isLoading, error } = useQuery<MyClassesResponse>({
    queryKey: ['myClasses'],
    queryFn: () => academicsService.getMyClasses(),
  });

  // ─── Loading ────────────────────────────────────────────────────────────────

  if (isLoading) {
    return (
      <div className="space-y-6 p-6">
        {/* Header skeleton */}
        <div className="space-y-2">
          <div className="h-8 w-48 bg-gray-200 rounded animate-pulse" />
          <div className="h-5 w-64 bg-gray-100 rounded animate-pulse" />
        </div>

        {/* Stats skeleton */}
        <div className="flex gap-4">
          <div className="h-16 w-40 bg-gray-100 rounded-xl animate-pulse" />
          <div className="h-16 w-40 bg-gray-100 rounded-xl animate-pulse" />
        </div>

        {/* Subject group skeleton */}
        <div className="space-y-8">
          <div className="h-5 w-36 bg-gray-200 rounded animate-pulse" />
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <SkeletonCard key={i} />
            ))}
          </div>
        </div>
      </div>
    );
  }

  // ─── Error ──────────────────────────────────────────────────────────────────

  if (error) {
    return (
      <div className="p-6">
        <div className="bg-red-50 text-red-700 rounded-lg p-4 text-sm">
          Failed to load your classes. Please try again.
        </div>
      </div>
    );
  }

  // ─── Data ───────────────────────────────────────────────────────────────────

  const assignments = data?.assignments ?? [];
  const totalSections = data?.total_sections ?? 0;
  const totalSubjects = assignments.length;

  // ─── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-8 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 tracking-tight">
            My Classes
          </h1>
          <div className="flex items-center gap-3 mt-1">
            {data?.academic_year && (
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-orange-100 text-tp-accent">
                {data.academic_year}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Summary stats */}
      {assignments.length > 0 && (
        <div className="flex flex-wrap gap-4">
          <div className="flex items-center gap-3 bg-orange-50 rounded-xl px-5 py-3">
            <Layers className="h-5 w-5 text-tp-accent" />
            <div>
              <p className="text-xl font-bold text-orange-700">{totalSections}</p>
              <p className="text-xs text-orange-500">
                Total {totalSections === 1 ? 'Section' : 'Sections'}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3 bg-blue-50 rounded-xl px-5 py-3">
            <GraduationCap className="h-5 w-5 text-blue-600" />
            <div>
              <p className="text-xl font-bold text-blue-700">{totalSubjects}</p>
              <p className="text-xs text-blue-500">
                {totalSubjects === 1 ? 'Subject' : 'Subjects'}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Empty state */}
      {assignments.length === 0 ? (
        <div className="text-center py-16 bg-gray-50 rounded-2xl border-2 border-dashed border-gray-200">
          <GraduationCap className="mx-auto h-12 w-12 text-gray-400" />
          <h3 className="mt-4 text-lg font-semibold text-gray-900">
            No teaching assignments
          </h3>
          <p className="mt-2 text-sm text-gray-500 max-w-md mx-auto">
            You don&apos;t have any class assignments yet. Contact your admin to
            set up teaching assignments.
          </p>
        </div>
      ) : (
        <div className="space-y-10">
          {assignments.map((assignment) => (
            <SubjectGroup
              key={assignment.assignment_id}
              assignment={assignment}
              onSectionClick={(sectionId) =>
                navigate(`/teacher/my-classes/section/${sectionId}`)
              }
            />
          ))}
        </div>
      )}
    </div>
  );
};

export default MyClassesPage;
