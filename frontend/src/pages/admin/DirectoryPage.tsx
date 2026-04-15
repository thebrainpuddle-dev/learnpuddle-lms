// src/pages/admin/DirectoryPage.tsx
//
// School Directory — visual card-based view of the entire school organized
// by grade band → grade → sections. Each section is a rich card showing
// class teacher, subject teachers, and student avatars at a glance.

import React, { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  UserGroupIcon,
  AcademicCapIcon,
  MagnifyingGlassIcon,
  BookOpenIcon,
} from '@heroicons/react/24/outline';
import { usePageTitle } from '../../hooks/usePageTitle';
import { Input } from '../../components/common';
import {
  academicsService,
  type SchoolOverviewResponse,
  type Section,
  type SectionStudentsResponse,
  type SectionTeachersResponse,
} from '../../services/academicsService';

// ── Avatar Initials ───────────────────────────────────────────────────

const AVATAR_COLORS = [
  'bg-blue-100 text-blue-700',
  'bg-emerald-100 text-emerald-700',
  'bg-amber-100 text-amber-700',
  'bg-rose-100 text-rose-700',
  'bg-purple-100 text-purple-700',
  'bg-cyan-100 text-cyan-700',
  'bg-orange-100 text-orange-700',
  'bg-teal-100 text-teal-700',
  'bg-pink-100 text-pink-700',
  'bg-indigo-100 text-indigo-700',
];

function getAvatarColor(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
  return AVATAR_COLORS[Math.abs(hash) % AVATAR_COLORS.length];
}

function Avatar({ firstName, lastName, size = 'sm' }: { firstName: string; lastName: string; size?: 'sm' | 'md' | 'lg' }) {
  const initials = `${firstName?.charAt(0) || ''}${lastName?.charAt(0) || ''}`.toUpperCase();
  const color = getAvatarColor(`${firstName}${lastName}`);
  const sizeClass = size === 'lg' ? 'h-12 w-12 text-sm' : size === 'md' ? 'h-9 w-9 text-xs' : 'h-7 w-7 text-[10px]';
  return (
    <div className={`${sizeClass} rounded-full ${color} flex items-center justify-center font-semibold flex-shrink-0`} title={`${firstName} ${lastName}`}>
      {initials}
    </div>
  );
}

// ── Section Card (loads its own data) ─────────────────────────────────

interface SectionCardProps {
  sectionId: string;
  sectionName: string;
  gradeName: string;
  gradeShortCode: string;
  studentCount: number;
  classTeacherName: string | null;
  accentColor: string;
}

const SectionCard: React.FC<SectionCardProps> = ({
  sectionId,
  sectionName,
  gradeName,
  gradeShortCode,
  studentCount,
  classTeacherName,
  accentColor,
}) => {
  const [expanded, setExpanded] = useState(false);

  const { data: studentsData } = useQuery<SectionStudentsResponse>({
    queryKey: ['directorySection', sectionId, 'students'],
    queryFn: () => academicsService.getSectionStudents(sectionId),
    enabled: expanded,
  });

  const { data: teachersData } = useQuery<SectionTeachersResponse>({
    queryKey: ['directorySection', sectionId, 'teachers'],
    queryFn: () => academicsService.getSectionTeachers(sectionId),
    enabled: expanded,
  });

  const students = studentsData?.students ?? [];
  const assignments = teachersData?.teachers ?? [];

  return (
    <div
      className="bg-white rounded-xl border border-gray-200 overflow-hidden hover:shadow-md transition-shadow cursor-pointer group"
      onClick={() => setExpanded(!expanded)}
    >
      {/* Card Header with accent stripe */}
      <div className="h-1.5" style={{ backgroundColor: accentColor }} />

      <div className="p-4">
        {/* Grade + Section */}
        <div className="flex items-start justify-between mb-3">
          <div>
            <h3 className="text-base font-bold text-gray-900 leading-tight">
              {gradeName}
              <span className="text-gray-400 font-normal"> — </span>
              <span className="text-gray-700">{sectionName}</span>
            </h3>
            <span
              className="inline-flex items-center mt-1 px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wider"
              style={{ backgroundColor: `${accentColor}15`, color: accentColor }}
            >
              {gradeShortCode}
            </span>
          </div>
          <div className="flex items-center gap-1.5 text-xs text-gray-500 bg-gray-50 rounded-full px-2.5 py-1">
            <UserGroupIcon className="h-3.5 w-3.5" />
            <span className="font-medium">{studentCount}</span>
          </div>
        </div>

        {/* Class Teacher */}
        {classTeacherName && (
          <div className="flex items-center gap-2 mb-3">
            <Avatar
              firstName={classTeacherName.split(' ')[0] || ''}
              lastName={classTeacherName.split(' ')[1] || ''}
              size="md"
            />
            <div className="min-w-0">
              <p className="text-xs text-gray-400 leading-tight">Class Teacher</p>
              <p className="text-sm font-medium text-gray-800 truncate">{classTeacherName}</p>
            </div>
          </div>
        )}

        {!classTeacherName && (
          <div className="flex items-center gap-2 mb-3 opacity-50">
            <div className="h-9 w-9 rounded-full bg-gray-100 flex items-center justify-center flex-shrink-0">
              <AcademicCapIcon className="h-4 w-4 text-gray-400" />
            </div>
            <p className="text-xs text-gray-400 italic">No class teacher assigned</p>
          </div>
        )}

        {/* Student Avatar Grid (preview — first 12) */}
        {!expanded && studentCount > 0 && (
          <div className="flex items-center gap-1 flex-wrap">
            {Array.from({ length: Math.min(studentCount, 12) }).map((_, i) => (
              <div
                key={i}
                className="h-6 w-6 rounded-full bg-gray-100 flex items-center justify-center text-[9px] font-medium text-gray-400"
              >
                {i + 1}
              </div>
            ))}
            {studentCount > 12 && (
              <div className="h-6 w-6 rounded-full bg-gray-200 flex items-center justify-center text-[9px] font-medium text-gray-500">
                +{studentCount - 12}
              </div>
            )}
          </div>
        )}

        {/* Expanded: full students + teachers */}
        {expanded && (
          <div className="mt-3 space-y-4" onClick={(e) => e.stopPropagation()}>
            {/* Subject Teachers */}
            {assignments.length > 0 && (
              <div>
                <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-2">Subject Teachers</p>
                <div className="flex flex-wrap gap-1.5">
                  {assignments.map((a) => (
                    <div
                      key={a.id}
                      className="inline-flex items-center gap-1.5 px-2 py-1 rounded-lg bg-gray-50 border border-gray-100 text-xs"
                    >
                      <Avatar
                        firstName={a.teacher_name.split(' ')[0] || ''}
                        lastName={a.teacher_name.split(' ')[1] || ''}
                        size="sm"
                      />
                      <div className="min-w-0">
                        <p className="text-[10px] text-gray-400 leading-tight">{a.subject_name}</p>
                        <p className="text-xs font-medium text-gray-700 truncate">{a.teacher_name}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Student Roster */}
            <div>
              <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-2">
                Students ({students.length})
              </p>
              {students.length === 0 ? (
                <p className="text-xs text-gray-400 italic">No students enrolled.</p>
              ) : (
                <div className="grid grid-cols-1 gap-1.5 max-h-64 overflow-y-auto pr-1 custom-scrollbar">
                  {students.map((s, idx) => (
                    <div
                      key={s.id}
                      className="flex items-center gap-2.5 px-2.5 py-1.5 rounded-lg hover:bg-gray-50 transition-colors"
                    >
                      <span className="text-[10px] text-gray-400 w-4 text-right flex-shrink-0">{idx + 1}</span>
                      <Avatar firstName={s.first_name} lastName={s.last_name} size="sm" />
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium text-gray-800 truncate">
                          {s.first_name} {s.last_name}
                        </p>
                      </div>
                      {s.student_id && (
                        <span className="text-[10px] text-gray-400 font-mono flex-shrink-0">{s.student_id}</span>
                      )}
                      {!s.is_active && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-50 text-red-500 font-medium flex-shrink-0">Inactive</span>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Expand hint */}
      <div className="px-4 py-2 bg-gray-50/50 border-t border-gray-100 text-center">
        <span className="text-[10px] font-medium text-gray-400 group-hover:text-gray-600 transition-colors">
          {expanded ? 'Click to collapse' : 'Click to view roster'}
        </span>
      </div>
    </div>
  );
};

// ── Main Component ────────────────────────────────────────────────────

export const DirectoryPage: React.FC = () => {
  usePageTitle('School Directory');
  const [search, setSearch] = useState('');

  const { data: overview, isLoading } = useQuery<SchoolOverviewResponse>({
    queryKey: ['schoolOverview'],
    queryFn: () => academicsService.getSchoolOverview(),
  });

  const { data: sectionsData } = useQuery<Section[]>({
    queryKey: ['directorySections'],
    queryFn: () => academicsService.getSections(),
  });

  const sections = useMemo(() => sectionsData ?? [], [sectionsData]);

  // Group sections under their grade within each band
  const groupedData = useMemo(() => {
    if (!overview?.grade_bands || sections.length === 0) return [];

    return overview.grade_bands.map((band) => ({
      ...band,
      grades: band.grades
        .map((grade) => ({
          ...grade,
          sections: sections.filter((s) => s.grade === grade.id),
        }))
        .filter((g) => g.sections.length > 0),
    })).filter((b) => b.grades.length > 0);
  }, [overview, sections]);

  // Summary stats
  const totalStudents = useMemo(
    () => overview?.grade_bands?.reduce((sum, b) => sum + b.grades.reduce((gs, g) => gs + (g.student_count ?? 0), 0), 0) ?? 0,
    [overview],
  );
  const totalGrades = overview?.grade_bands?.reduce((sum, b) => sum + b.grades.length, 0) ?? 0;

  // Filter sections by search
  const filterActive = search.length > 0;

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="h-8 w-56 bg-gray-200 rounded animate-pulse" />
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => <div key={i} className="h-20 bg-gray-100 rounded-xl animate-pulse" />)}
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3, 4, 5, 6].map((i) => <div key={i} className="h-48 bg-gray-100 rounded-xl animate-pulse" />)}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">School Directory</h1>
          <p className="mt-1 text-sm text-gray-500">
            {overview?.school_name || 'School'} &middot; {overview?.academic_year || ''}
          </p>
        </div>
        <div className="w-full sm:w-80">
          <Input
            id="directory-search"
            name="directory_search"
            autoComplete="off"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by name, grade, or section..."
            leftIcon={<MagnifyingGlassIcon className="h-5 w-5" />}
          />
        </div>
      </div>

      {/* Summary Strip */}
      <div className="flex items-center gap-6 flex-wrap">
        <Stat label="Grade Bands" value={overview?.grade_bands?.length ?? 0} />
        <Stat label="Grades" value={totalGrades} />
        <Stat label="Sections" value={sections.length} />
        <Stat label="Students" value={totalStudents} />
      </div>

      {/* Grade Band → Grade → Section Cards */}
      {groupedData.length === 0 ? (
        <div className="text-center py-16">
          <AcademicCapIcon className="h-14 w-14 text-gray-200 mx-auto mb-4" />
          <p className="text-gray-500 font-medium">No academic structure configured</p>
          <p className="text-gray-400 text-sm mt-1">Set up grade bands and sections in School settings first.</p>
        </div>
      ) : (
        <div className="space-y-10">
          {groupedData.map((band) => {
            const accentColor = band.theme_config?.accent_color || '#6366f1';

            // Filter by search
            const filteredGrades = band.grades.map((grade) => ({
              ...grade,
              sections: grade.sections.filter((s) => {
                if (!filterActive) return true;
                const q = search.toLowerCase();
                return (
                  grade.name.toLowerCase().includes(q) ||
                  s.name.toLowerCase().includes(q) ||
                  (s.class_teacher_name && s.class_teacher_name.toLowerCase().includes(q)) ||
                  band.name.toLowerCase().includes(q)
                );
              }),
            })).filter((g) => g.sections.length > 0);

            if (filteredGrades.length === 0) return null;

            return (
              <section key={band.id}>
                {/* Band Header */}
                <div className="flex items-center gap-3 mb-5">
                  <div className="h-10 w-10 rounded-xl flex items-center justify-center" style={{ backgroundColor: `${accentColor}15` }}>
                    <BookOpenIcon className="h-5 w-5" style={{ color: accentColor }} />
                  </div>
                  <div>
                    <h2 className="text-lg font-bold text-gray-900">{band.name}</h2>
                    <p className="text-xs text-gray-500">
                      {band.curriculum_framework.replace(/_/g, ' ')} &middot;{' '}
                      {filteredGrades.reduce((sum, g) => sum + g.sections.length, 0)} sections &middot;{' '}
                      {filteredGrades.reduce((sum, g) => sum + g.sections.reduce((ss, s) => ss + s.student_count, 0), 0)} students
                    </p>
                  </div>
                </div>

                {/* Section Cards Grid */}
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  {filteredGrades.flatMap((grade) =>
                    grade.sections.map((section) => (
                      <SectionCard
                        key={section.id}
                        sectionId={section.id}
                        sectionName={section.name}
                        gradeName={grade.name}
                        gradeShortCode={grade.short_code}
                        studentCount={section.student_count}
                        classTeacherName={section.class_teacher_name}
                        accentColor={accentColor}
                      />
                    )),
                  )}
                </div>
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
};

// ── Stat Chip ─────────────────────────────────────────────────────────

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-2xl font-bold text-gray-900">{value}</span>
      <span className="text-xs text-gray-500 uppercase tracking-wide font-medium">{label}</span>
    </div>
  );
}

export default DirectoryPage;
