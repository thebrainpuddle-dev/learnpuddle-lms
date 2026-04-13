// src/pages/admin/SchoolViewPage.tsx
//
// Level 1 — School Overview
// Displays grade cards grouped by grade band (Early Years, Primary, Middle, High School).
// Each card shows grade name, student count, and section count.
// Clicking a grade card navigates to /admin/school/grade/:gradeId.

import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  AcademicCapIcon,
  Cog6ToothIcon,
  UserGroupIcon,
  RectangleStackIcon,
  BookOpenIcon,
} from '@heroicons/react/24/outline';
import { usePageTitle } from '../../hooks/usePageTitle';
import {
  academicsService,
  type SchoolOverviewResponse,
} from '../../services/academicsService';

// ─── Skeleton Card ──────────────────────────────────────────────────────────

const GradeCardSkeleton: React.FC = () => (
  <div className="bg-white rounded-xl shadow-sm border-l-4 border-gray-200 p-5 animate-pulse">
    <div className="flex items-start justify-between mb-3">
      <div>
        <div className="h-5 w-28 bg-gray-200 rounded mb-2" />
        <div className="h-4 w-14 bg-gray-100 rounded-full" />
      </div>
      <div className="h-5 w-5 bg-gray-100 rounded" />
    </div>
    <div className="space-y-2 mt-4">
      <div className="h-4 w-24 bg-gray-100 rounded" />
      <div className="h-4 w-20 bg-gray-100 rounded" />
    </div>
  </div>
);

const LoadingSkeleton: React.FC = () => (
  <div className="space-y-8 p-6">
    {/* Header skeleton */}
    <div className="flex items-center justify-between">
      <div>
        <div className="h-8 w-48 bg-gray-200 rounded animate-pulse" />
        <div className="h-5 w-24 bg-gray-100 rounded-full animate-pulse mt-2" />
      </div>
      <div className="h-10 w-10 bg-gray-100 rounded-lg animate-pulse" />
    </div>

    {/* Band section skeleton */}
    {[1, 2].map((band) => (
      <div key={band} className="space-y-4">
        <div className="flex items-center gap-3">
          <div className="w-1 h-8 bg-gray-200 rounded-full animate-pulse" />
          <div>
            <div className="h-5 w-32 bg-gray-200 rounded animate-pulse" />
            <div className="h-3 w-24 bg-gray-100 rounded animate-pulse mt-1" />
          </div>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <GradeCardSkeleton key={i} />
          ))}
        </div>
      </div>
    ))}
  </div>
);

// ─── Empty State ────────────────────────────────────────────────────────────

const EmptyState: React.FC<{ onSetup: () => void }> = ({ onSetup }) => (
  <div className="flex flex-col items-center justify-center py-20 px-6">
    <div className="relative mb-6">
      {/* Decorative background circles */}
      <div className="absolute -inset-4 bg-indigo-50 rounded-full opacity-60" />
      <div className="absolute -inset-8 bg-indigo-50/40 rounded-full" />
      <div className="relative bg-white rounded-full p-5 shadow-sm border border-gray-100">
        <AcademicCapIcon className="h-12 w-12 text-indigo-400" />
      </div>
    </div>
    <h3 className="text-xl font-semibold text-gray-900 mt-2">
      No academic structure configured
    </h3>
    <p className="mt-2 text-sm text-gray-500 max-w-md text-center leading-relaxed">
      Add grade bands and grades to get started. Grade bands group related grades
      together (e.g., Early Years, Primary, Middle School) and define the
      curriculum framework for each level.
    </p>
    <button
      onClick={onSetup}
      className="mt-8 inline-flex items-center gap-2 px-5 py-2.5 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 transition-colors shadow-sm"
    >
      <Cog6ToothIcon className="h-4 w-4" />
      Configure Academic Structure
    </button>
  </div>
);

// ─── Grade Card ─────────────────────────────────────────────────────────────

interface GradeCardProps {
  gradeId: string;
  name: string;
  shortCode: string;
  studentCount: number;
  sectionCount: number;
  courseCount?: number;
  accentColor: string;
  onClick: () => void;
}

const GradeCard: React.FC<GradeCardProps> = ({
  name,
  shortCode,
  studentCount,
  sectionCount,
  courseCount,
  accentColor,
  onClick,
}) => {
  return (
    <button
      onClick={onClick}
      className="group relative bg-white rounded-xl shadow-sm border border-gray-100 border-l-4 p-5 text-left hover:shadow-md focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 transition-all duration-200"
      style={{ borderLeftColor: accentColor }}
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <div className="min-w-0">
          <h3 className="text-base font-semibold text-gray-900 truncate group-hover:text-indigo-600 transition-colors">
            {name}
          </h3>
          <span
            className="inline-flex items-center mt-1 px-2 py-0.5 rounded-full text-xs font-medium"
            style={{
              backgroundColor: `${accentColor}15`,
              color: accentColor,
            }}
          >
            {shortCode}
          </span>
        </div>

        {/* Hover arrow indicator */}
        <div className="flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
          <svg
            className="h-5 w-5 text-gray-400"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M9 5l7 7-7 7"
            />
          </svg>
        </div>
      </div>

      {/* Stats */}
      <div className="space-y-2 mt-4">
        <div className="flex items-center gap-2 text-sm text-gray-600">
          <UserGroupIcon className="h-4 w-4 text-gray-400 flex-shrink-0" />
          <span>
            {studentCount.toLocaleString()}{' '}
            {studentCount === 1 ? 'student' : 'students'}
          </span>
        </div>
        <div className="flex items-center gap-2 text-sm text-gray-600">
          <RectangleStackIcon className="h-4 w-4 text-gray-400 flex-shrink-0" />
          <span>
            {sectionCount} {sectionCount === 1 ? 'section' : 'sections'}
          </span>
        </div>
        {courseCount !== undefined && courseCount > 0 && (
          <div className="flex items-center gap-2 text-sm text-gray-600">
            <BookOpenIcon className="h-4 w-4 text-gray-400 flex-shrink-0" />
            <span>
              {courseCount} {courseCount === 1 ? 'course' : 'courses'}
            </span>
          </div>
        )}
      </div>
    </button>
  );
};

// ─── Grade Band Section ─────────────────────────────────────────────────────

interface GradeBandSectionProps {
  bandName: string;
  curriculumFramework: string;
  accentColor: string;
  totalStudents: number;
  grades: Array<{
    id: string;
    name: string;
    short_code: string;
    student_count: number;
    section_count: number;
    course_count?: number;
  }>;
  onGradeClick: (gradeId: string) => void;
}

const GradeBandSection: React.FC<GradeBandSectionProps> = ({
  bandName,
  curriculumFramework,
  accentColor,
  totalStudents,
  grades,
  onGradeClick,
}) => {
  return (
    <section>
      {/* Band header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div
            className="w-1.5 h-8 rounded-full"
            style={{ backgroundColor: accentColor }}
          />
          <div>
            <h2 className="text-lg font-semibold text-gray-900">{bandName}</h2>
            <div className="flex items-center gap-2 mt-0.5">
              <span className="text-xs text-gray-500">
                {curriculumFramework.replace(/_/g, ' ')}
              </span>
              <span className="text-xs text-gray-400">&middot;</span>
              <span className="text-xs text-gray-500">
                {totalStudents.toLocaleString()}{' '}
                {totalStudents === 1 ? 'student' : 'students'}
              </span>
              <span className="text-xs text-gray-400">&middot;</span>
              <span className="text-xs text-gray-500">
                {grades.length} {grades.length === 1 ? 'grade' : 'grades'}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Grade cards grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
        {grades.map((grade) => (
          <GradeCard
            key={grade.id}
            gradeId={grade.id}
            name={grade.name}
            shortCode={grade.short_code}
            studentCount={grade.student_count}
            sectionCount={grade.section_count}
            courseCount={grade.course_count}
            accentColor={accentColor}
            onClick={() => onGradeClick(grade.id)}
          />
        ))}
      </div>
    </section>
  );
};

// ─── Error State ────────────────────────────────────────────────────────────

const ErrorState: React.FC<{ onRetry: () => void }> = ({ onRetry }) => (
  <div className="p-6">
    <div className="bg-red-50 border border-red-200 rounded-xl p-6 text-center max-w-lg mx-auto">
      <div className="mx-auto h-12 w-12 rounded-full bg-red-100 flex items-center justify-center mb-4">
        <svg
          className="h-6 w-6 text-red-500"
          fill="none"
          viewBox="0 0 24 24"
          strokeWidth="1.5"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z"
          />
        </svg>
      </div>
      <h3 className="text-lg font-semibold text-gray-900 mb-2">
        Failed to load school data
      </h3>
      <p className="text-sm text-gray-500 mb-4">
        There was an error loading the academic structure. Please check your
        connection and try again.
      </p>
      <button
        onClick={onRetry}
        className="inline-flex items-center px-4 py-2 bg-red-600 text-white text-sm font-medium rounded-lg hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500 transition-colors"
      >
        Try Again
      </button>
    </div>
  </div>
);

// ─── Main Component ─────────────────────────────────────────────────────────

export const SchoolViewPage: React.FC = () => {
  usePageTitle('School');
  const navigate = useNavigate();

  const {
    data: overview,
    isLoading,
    error,
    refetch,
  } = useQuery<SchoolOverviewResponse>({
    queryKey: ['schoolOverview'],
    queryFn: () => academicsService.getSchoolOverview(),
  });

  // ── Loading State ──────────────────────────────────────────────────────

  if (isLoading) {
    return <LoadingSkeleton />;
  }

  // ── Error State ────────────────────────────────────────────────────────

  if (error) {
    return <ErrorState onRetry={() => refetch()} />;
  }

  // ── Derived Data ───────────────────────────────────────────────────────

  const hasGradeBands =
    overview?.grade_bands && overview.grade_bands.length > 0;

  const handleGradeClick = (gradeId: string) => {
    navigate(`/admin/school/grade/${gradeId}`);
  };

  // ── Render ─────────────────────────────────────────────────────────────

  return (
    <div className="space-y-8 p-6">
      {/* ── Top Bar ────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">
            {overview?.school_name || 'School'}
          </h1>
          {overview?.academic_year && (
            <span className="inline-flex items-center mt-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-indigo-100 text-indigo-800">
              {overview.academic_year}
            </span>
          )}
        </div>
        <button
          onClick={() => navigate('/admin/settings')}
          className="p-2.5 text-gray-400 hover:text-gray-600 rounded-lg hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 transition-colors"
          title="School Settings"
          aria-label="School settings"
        >
          <Cog6ToothIcon className="h-6 w-6" />
        </button>
      </div>

      {/* ── Content ────────────────────────────────────────────────────── */}
      {!hasGradeBands ? (
        <EmptyState onSetup={() => navigate('/admin/settings')} />
      ) : (
        <div className="space-y-10">
          {overview!.grade_bands.map((band) => {
            const accentColor =
              band.theme_config?.accent_color || '#6366f1';
            const totalStudents = band.grades.reduce(
              (sum, g) => sum + (g.student_count ?? 0),
              0,
            );

            return (
              <GradeBandSection
                key={band.id}
                bandName={band.name}
                curriculumFramework={band.curriculum_framework}
                accentColor={accentColor}
                totalStudents={totalStudents}
                grades={band.grades}
                onGradeClick={handleGradeClick}
              />
            );
          })}
        </div>
      )}
    </div>
  );
};

export default SchoolViewPage;
