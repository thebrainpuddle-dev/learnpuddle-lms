// src/pages/admin/GradeDetailPage.tsx
//
// Admin Level 2 — Grade Detail page.
// Shows section cards within a specific grade with actions to add/edit/delete
// sections and import students via CSV.
// URL: /admin/school/grade/:gradeId

import React, { useState, useRef } from 'react';
import { useNavigate, useParams, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { z } from 'zod';
import {
  AcademicCapIcon,
  PlusIcon,
  ArrowLeftIcon,
  ArrowUpTrayIcon,
  UserGroupIcon,
  UsersIcon,
  BookOpenIcon,
  ChevronRightIcon,
  XMarkIcon,
  UserIcon,
} from '@heroicons/react/24/outline';
import { Button, Input, useToast } from '../../components/common';
import { usePageTitle } from '../../hooks/usePageTitle';
import {
  academicsService,
  type Section,
  type Grade,
  type SchoolOverviewResponse,
} from '../../services/academicsService';

// ─── Validation ──────────────────────────────────────────────────────────────

const sectionFormSchema = z.object({
  name: z
    .string()
    .min(1, 'Section name is required')
    .max(50, 'Section name must be 50 characters or fewer'),
  academic_year: z
    .string()
    .min(1, 'Academic year is required')
    .max(20, 'Academic year must be 20 characters or fewer'),
  class_teacher: z.string().optional(),
});

type SectionFormData = z.infer<typeof sectionFormSchema>;

// ─── Grade Band Color Map ────────────────────────────────────────────────────

const GRADE_BAND_COLORS: Record<
  string,
  { border: string; bg: string; text: string; badge: string }
> = {
  primary: {
    border: 'border-l-emerald-500',
    bg: 'bg-emerald-50',
    text: 'text-emerald-700',
    badge: 'bg-emerald-100 text-emerald-800',
  },
  middle: {
    border: 'border-l-blue-500',
    bg: 'bg-blue-50',
    text: 'text-blue-700',
    badge: 'bg-blue-100 text-blue-800',
  },
  secondary: {
    border: 'border-l-purple-500',
    bg: 'bg-purple-50',
    text: 'text-purple-700',
    badge: 'bg-purple-100 text-purple-800',
  },
  senior: {
    border: 'border-l-amber-500',
    bg: 'bg-amber-50',
    text: 'text-amber-700',
    badge: 'bg-amber-100 text-amber-800',
  },
};

const DEFAULT_BAND_COLORS = {
  border: 'border-l-indigo-500',
  bg: 'bg-indigo-50',
  text: 'text-indigo-700',
  badge: 'bg-indigo-100 text-indigo-800',
};

function getBandColors(bandName?: string) {
  if (!bandName) return DEFAULT_BAND_COLORS;
  const key = bandName.toLowerCase();
  for (const [k, v] of Object.entries(GRADE_BAND_COLORS)) {
    if (key.includes(k)) return v;
  }
  return DEFAULT_BAND_COLORS;
}

// ─── Skeleton Loader ─────────────────────────────────────────────────────────

const SectionCardSkeleton: React.FC = () => (
  <div className="bg-white rounded-xl border border-gray-200 p-5 animate-pulse">
    <div className="flex items-start justify-between mb-4">
      <div className="flex items-center gap-3">
        <div className="h-12 w-12 rounded-lg bg-gray-200" />
        <div>
          <div className="h-4 w-20 bg-gray-200 rounded mb-2" />
          <div className="h-3 w-32 bg-gray-100 rounded" />
        </div>
      </div>
      <div className="h-6 w-6 bg-gray-100 rounded" />
    </div>
    <div className="grid grid-cols-3 gap-3 mt-4">
      <div className="h-3 w-16 bg-gray-100 rounded" />
      <div className="h-3 w-20 bg-gray-100 rounded" />
      <div className="h-3 w-14 bg-gray-100 rounded" />
    </div>
  </div>
);

// ─── Actions Dropdown ────────────────────────────────────────────────────────

interface ActionsDropdownProps {
  section: Section;
  onEdit: (section: Section) => void;
  onDelete: (section: Section) => void;
}

const ActionsDropdown: React.FC<ActionsDropdownProps> = ({
  section,
  onEdit,
  onDelete,
}) => {
  const [open, setOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(e.target as Node)
      ) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  return (
    <div ref={dropdownRef} className="relative">
      <button
        onClick={(e) => {
          e.stopPropagation();
          setOpen((prev) => !prev);
        }}
        className="p-1 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
        aria-label={`Actions for Section ${section.name}`}
      >
        <svg className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
          <path d="M10 6a2 2 0 110-4 2 2 0 010 4zM10 12a2 2 0 110-4 2 2 0 010 4zM10 18a2 2 0 110-4 2 2 0 010 4z" />
        </svg>
      </button>
      {open && (
        <div className="absolute right-0 top-full mt-1 w-36 bg-white border border-gray-200 rounded-lg shadow-lg z-20 py-1">
          <button
            onClick={(e) => {
              e.stopPropagation();
              setOpen(false);
              onEdit(section);
            }}
            className="w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
          >
            Edit
          </button>
          <button
            onClick={(e) => {
              e.stopPropagation();
              setOpen(false);
              onDelete(section);
            }}
            className="w-full text-left px-4 py-2 text-sm text-red-600 hover:bg-red-50 transition-colors"
          >
            Delete
          </button>
        </div>
      )}
    </div>
  );
};

// ─── Spinner SVG ─────────────────────────────────────────────────────────────

const Spinner: React.FC<{ className?: string }> = ({ className = 'h-4 w-4' }) => (
  <svg
    className={`animate-spin ${className}`}
    xmlns="http://www.w3.org/2000/svg"
    fill="none"
    viewBox="0 0 24 24"
  >
    <circle
      className="opacity-25"
      cx="12"
      cy="12"
      r="10"
      stroke="currentColor"
      strokeWidth="4"
    />
    <path
      className="opacity-75"
      fill="currentColor"
      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
    />
  </svg>
);

// ─── Main Page ───────────────────────────────────────────────────────────────

export const GradeDetailPage: React.FC = () => {
  const { gradeId } = useParams<{ gradeId: string }>();
  const navigate = useNavigate();
  const toast = useToast();
  const queryClient = useQueryClient();

  // Modal states
  const [showAddModal, setShowAddModal] = useState(false);
  const [showImportModal, setShowImportModal] = useState(false);
  const [editingSection, setEditingSection] = useState<Section | null>(null);
  const [deletingSection, setDeletingSection] = useState<Section | null>(null);

  // Form state
  const [formData, setFormData] = useState<SectionFormData>({
    name: '',
    academic_year: '',
    class_teacher: '',
  });
  const [formErrors, setFormErrors] = useState<
    Partial<Record<keyof SectionFormData, string>>
  >({});

  // Import modal state
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importSectionId, setImportSectionId] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ── Queries ────────────────────────────────────────────────────────────

  const { data: overview, isLoading: overviewLoading } =
    useQuery<SchoolOverviewResponse>({
      queryKey: ['schoolOverview'],
      queryFn: () => academicsService.getSchoolOverview(),
    });

  // Resolve the grade and its band from the overview
  const gradeInfo = React.useMemo(() => {
    if (!overview?.grade_bands || !gradeId) return null;
    for (const band of overview.grade_bands) {
      const found = band.grades.find((g) => g.id === gradeId);
      if (found) {
        return {
          grade: found,
          bandName: band.name,
          bandAccentColor: band.theme_config?.accent_color,
          academicYear: overview.academic_year,
          schoolName: overview.school_name,
        };
      }
    }
    return null;
  }, [overview, gradeId]);

  const grade = gradeInfo?.grade ?? null;

  usePageTitle(grade ? `${grade.name} - Sections` : 'Grade Detail');

  const {
    data: sections,
    isLoading: sectionsLoading,
    error: sectionsError,
  } = useQuery({
    queryKey: ['sections', gradeId],
    queryFn: () => academicsService.getSections(gradeId!),
    enabled: !!gradeId,
  });

  const bandColors = getBandColors(gradeInfo?.bandName);

  // ── Mutations ──────────────────────────────────────────────────────────

  const createSectionMutation = useMutation({
    mutationFn: (data: {
      grade: string;
      name: string;
      academic_year: string;
      class_teacher?: string;
    }) => academicsService.createSection(data),
    onSuccess: (newSection) => {
      queryClient.invalidateQueries({ queryKey: ['sections', gradeId] });
      queryClient.invalidateQueries({ queryKey: ['grades'] });
      queryClient.invalidateQueries({ queryKey: ['schoolOverview'] });
      closeModal();
      toast.success(
        'Section created',
        `"Section ${newSection.name}" has been added to ${grade?.name ?? 'the grade'}.`,
      );
    },
    onError: (err: any) => {
      const detail = err?.response?.data;
      const message =
        typeof detail === 'object'
          ? Object.values(detail).flat().join(', ')
          : 'Please check the details and try again.';
      toast.error('Failed to create section', message);
    },
  });

  const updateSectionMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<Section> }) =>
      academicsService.updateSection(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sections', gradeId] });
      queryClient.invalidateQueries({ queryKey: ['schoolOverview'] });
      closeModal();
      toast.success(
        'Section updated',
        'The section has been updated successfully.',
      );
    },
    onError: () => {
      toast.error('Failed to update section', 'Please try again.');
    },
  });

  const deleteSectionMutation = useMutation({
    mutationFn: (id: string) => academicsService.deleteSection(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sections', gradeId] });
      queryClient.invalidateQueries({ queryKey: ['grades'] });
      queryClient.invalidateQueries({ queryKey: ['schoolOverview'] });
      setDeletingSection(null);
      toast.success('Section deleted', 'The section has been removed.');
    },
    onError: () => {
      toast.error('Failed to delete section', 'Please try again.');
    },
  });

  const importStudentsMutation = useMutation({
    mutationFn: ({ sectionId, file }: { sectionId: string; file: File }) =>
      academicsService.importStudents(sectionId, file),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['sections', gradeId] });
      const parts = [
        result.created > 0 ? `${result.created} created` : null,
        result.skipped > 0 ? `${result.skipped} skipped` : null,
        result.errors.length > 0 ? `${result.errors.length} errors` : null,
      ]
        .filter(Boolean)
        .join(', ');
      toast.success(
        'Import complete',
        `${result.total_rows} rows processed: ${parts}.`,
      );
      if (result.errors.length === 0) {
        setShowImportModal(false);
        setImportFile(null);
        setImportSectionId('');
      }
    },
    onError: () => {
      toast.error(
        'Import failed',
        'Please check your CSV file format and try again.',
      );
    },
  });

  // ── Helpers ────────────────────────────────────────────────────────────

  const closeModal = () => {
    setShowAddModal(false);
    setEditingSection(null);
    setFormData({ name: '', academic_year: '', class_teacher: '' });
    setFormErrors({});
  };

  const openAddModal = () => {
    setEditingSection(null);
    setFormData({
      name: '',
      academic_year: gradeInfo?.academicYear ?? new Date().getFullYear().toString(),
      class_teacher: '',
    });
    setFormErrors({});
    setShowAddModal(true);
  };

  const openEditModal = (section: Section) => {
    setEditingSection(section);
    setFormData({
      name: section.name,
      academic_year: section.academic_year,
      class_teacher: section.class_teacher_name ?? '',
    });
    setFormErrors({});
    setShowAddModal(true);
  };

  const handleFormChange = (field: keyof SectionFormData, value: string) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
    if (formErrors[field]) {
      setFormErrors((prev) => ({ ...prev, [field]: undefined }));
    }
  };

  const handleSubmitSection = (e: React.FormEvent) => {
    e.preventDefault();

    const result = sectionFormSchema.safeParse(formData);
    if (!result.success) {
      const fieldErrors: Partial<Record<keyof SectionFormData, string>> = {};
      for (const issue of result.error.issues) {
        const field = issue.path[0] as keyof SectionFormData;
        if (!fieldErrors[field]) {
          fieldErrors[field] = issue.message;
        }
      }
      setFormErrors(fieldErrors);
      return;
    }

    const payload = {
      name: result.data.name.trim(),
      academic_year: result.data.academic_year.trim(),
      ...(result.data.class_teacher?.trim()
        ? { class_teacher: result.data.class_teacher.trim() }
        : {}),
    };

    if (editingSection) {
      updateSectionMutation.mutate({
        id: editingSection.id,
        data: payload,
      });
    } else {
      createSectionMutation.mutate({
        grade: gradeId!,
        ...payload,
      });
    }
  };

  const handleImportSubmit = () => {
    if (!importSectionId) {
      toast.warning(
        'Select a section',
        'Please select a section to import students into.',
      );
      return;
    }
    if (!importFile) {
      toast.warning(
        'Select a file',
        'Please select a CSV file to upload.',
      );
      return;
    }
    importStudentsMutation.mutate({
      sectionId: importSectionId,
      file: importFile,
    });
  };

  const handleSectionClick = (sectionId: string) => {
    navigate(`/admin/school/section/${sectionId}`);
  };

  // ── Loading State ──────────────────────────────────────────────────────

  const isLoading = overviewLoading || sectionsLoading;

  if (isLoading) {
    return (
      <div className="space-y-6">
        {/* Header skeleton */}
        <div className="animate-pulse">
          <div className="h-4 w-48 bg-gray-200 rounded mb-4" />
          <div className="flex items-center justify-between">
            <div>
              <div className="h-7 w-40 bg-gray-200 rounded mb-2" />
              <div className="h-4 w-56 bg-gray-100 rounded" />
            </div>
            <div className="flex gap-3">
              <div className="h-10 w-36 bg-gray-200 rounded-lg" />
              <div className="h-10 w-32 bg-gray-200 rounded-lg" />
            </div>
          </div>
        </div>

        {/* Cards skeleton */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <SectionCardSkeleton key={i} />
          ))}
        </div>
      </div>
    );
  }

  // ── Error State ────────────────────────────────────────────────────────

  if (sectionsError) {
    return (
      <div className="space-y-6">
        <div>
          <Link
            to="/admin/school"
            className="inline-flex items-center text-sm text-gray-500 hover:text-gray-700 mb-4"
          >
            <ArrowLeftIcon className="h-4 w-4 mr-1" />
            Back to School
          </Link>
        </div>
        <div className="bg-white rounded-xl border border-red-200 p-8 text-center">
          <div className="mx-auto h-12 w-12 rounded-full bg-red-50 flex items-center justify-center mb-4">
            <XMarkIcon className="h-6 w-6 text-red-500" />
          </div>
          <h2 className="text-lg font-semibold text-gray-900 mb-2">
            Failed to load sections
          </h2>
          <p className="text-sm text-gray-500 mb-4">
            There was an error loading section data. Please try again.
          </p>
          <button
            onClick={() =>
              queryClient.invalidateQueries({
                queryKey: ['sections', gradeId],
              })
            }
            className="inline-flex items-center px-4 py-2 bg-primary-600 text-white text-sm font-medium rounded-lg hover:bg-primary-700 transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  // ── Grade not found ────────────────────────────────────────────────────

  if (!grade && !overviewLoading) {
    return (
      <div className="space-y-6">
        <div>
          <Link
            to="/admin/school"
            className="inline-flex items-center text-sm text-gray-500 hover:text-gray-700 mb-4"
          >
            <ArrowLeftIcon className="h-4 w-4 mr-1" />
            Back to School
          </Link>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-8 text-center">
          <div className="mx-auto h-12 w-12 rounded-full bg-gray-50 flex items-center justify-center mb-4">
            <AcademicCapIcon className="h-6 w-6 text-gray-400" />
          </div>
          <h2 className="text-lg font-semibold text-gray-900 mb-2">
            Grade not found
          </h2>
          <p className="text-sm text-gray-500">
            The grade you are looking for does not exist or has been removed.
          </p>
        </div>
      </div>
    );
  }

  // ── Render ─────────────────────────────────────────────────────────────

  const sectionList = sections ?? [];
  const isMutating =
    createSectionMutation.isPending || updateSectionMutation.isPending;

  return (
    <div className="space-y-6">
      {/* ── Breadcrumb ──────────────────────────────────────────────────── */}
      <nav className="flex items-center gap-2 text-sm" aria-label="Breadcrumb">
        <Link
          to="/admin/school"
          className="text-gray-500 hover:text-primary-600 transition-colors font-medium"
        >
          School
        </Link>
        <ChevronRightIcon className="h-4 w-4 text-gray-400 flex-shrink-0" />
        <span className="text-gray-900 font-medium">
          {grade?.name ?? 'Grade'}
        </span>
      </nav>

      {/* ── Header ──────────────────────────────────────────────────────── */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/admin/school')}
            className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
            aria-label="Back to school overview"
          >
            <ArrowLeftIcon className="h-5 w-5" />
          </button>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold text-gray-900">
                {grade?.name}
              </h1>
              {gradeInfo?.bandName && (
                <span
                  className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${bandColors.badge}`}
                >
                  {gradeInfo.bandName}
                </span>
              )}
            </div>
            <p className="mt-1 text-sm text-gray-500">
              {sectionList.length}{' '}
              {sectionList.length === 1 ? 'section' : 'sections'}
              {' '}&middot;{' '}
              {grade?.student_count ?? 0}{' '}
              {(grade?.student_count ?? 0) === 1 ? 'student' : 'students'}
            </p>
          </div>
        </div>

        <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:items-center">
          <button
            onClick={() => setShowImportModal(true)}
            disabled={sectionList.length === 0}
            className="inline-flex items-center justify-center px-4 py-2 text-sm font-medium rounded-lg border-2 border-gray-300 text-gray-700 hover:bg-gray-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed w-full sm:w-auto"
          >
            <ArrowUpTrayIcon className="h-4 w-4 mr-2" />
            Import CSV
          </button>
          <button
            onClick={openAddModal}
            className="inline-flex items-center justify-center px-4 py-2 text-sm font-medium rounded-lg bg-primary-600 hover:bg-primary-700 text-white transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 w-full sm:w-auto"
          >
            <PlusIcon className="h-4 w-4 mr-2" />
            Add Section
          </button>
        </div>
      </div>

      {/* ── Section Cards Grid ──────────────────────────────────────────── */}
      {sectionList.length === 0 ? (
        <div className="bg-white rounded-xl border border-gray-200 p-12 text-center">
          <div className="mx-auto h-16 w-16 rounded-full bg-gray-50 flex items-center justify-center mb-4">
            <UserGroupIcon className="h-8 w-8 text-gray-300" />
          </div>
          <h3 className="text-lg font-semibold text-gray-900 mb-2">
            No sections for this grade
          </h3>
          <p className="text-sm text-gray-500 mb-6 max-w-sm mx-auto">
            Create the first section to start organizing students within{' '}
            {grade?.name ?? 'this grade'}. Each section can have its own class
            teacher and students.
          </p>
          <button
            onClick={openAddModal}
            className="inline-flex items-center px-4 py-2 bg-primary-600 text-white text-sm font-medium rounded-lg hover:bg-primary-700 transition-colors"
          >
            <PlusIcon className="h-4 w-4 mr-2" />
            Create First Section
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {sectionList.map((section) => (
            <div
              key={section.id}
              onClick={() => handleSectionClick(section.id)}
              className={`group bg-white rounded-xl border border-gray-200 hover:border-gray-300 shadow-sm hover:shadow-md transition-all cursor-pointer border-l-4 ${bandColors.border}`}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  handleSectionClick(section.id);
                }
              }}
              aria-label={`${grade?.name} - Section ${section.name}`}
            >
              <div className="p-5">
                {/* Section header */}
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-3 min-w-0">
                    <div
                      className={`h-12 w-12 rounded-lg flex items-center justify-center text-lg font-bold ${bandColors.bg} ${bandColors.text} flex-shrink-0`}
                    >
                      {section.name.charAt(0).toUpperCase()}
                    </div>
                    <div className="min-w-0">
                      <h3 className="text-base font-semibold text-gray-900 truncate group-hover:text-primary-600 transition-colors">
                        Section {section.name}
                      </h3>
                      <p className="text-xs text-gray-500 truncate">
                        {grade?.name} &middot; AY {section.academic_year}
                      </p>
                    </div>
                  </div>
                  <ActionsDropdown
                    section={section}
                    onEdit={openEditModal}
                    onDelete={(s) => setDeletingSection(s)}
                  />
                </div>

                {/* Stats row */}
                <div className="grid grid-cols-3 gap-2 mt-4 pt-3 border-t border-gray-100">
                  {/* Student count */}
                  <div className="flex flex-col items-center gap-1 text-center">
                    <UsersIcon className="h-4 w-4 text-gray-400" />
                    <span className="text-sm font-semibold text-gray-900">
                      {section.student_count}
                    </span>
                    <span className="text-[11px] text-gray-500 leading-tight">
                      {section.student_count === 1 ? 'Student' : 'Students'}
                    </span>
                  </div>

                  {/* Class teacher */}
                  <div className="flex flex-col items-center gap-1 text-center">
                    <UserIcon className="h-4 w-4 text-gray-400" />
                    <span
                      className={`text-sm font-semibold truncate max-w-full ${
                        section.class_teacher_name
                          ? 'text-gray-900'
                          : 'text-gray-300'
                      }`}
                      title={section.class_teacher_name ?? 'Unassigned'}
                    >
                      {section.class_teacher_name
                        ? section.class_teacher_name.split(' ')[0]
                        : '--'}
                    </span>
                    <span className="text-[11px] text-gray-500 leading-tight">
                      Teacher
                    </span>
                  </div>

                  {/* Course count */}
                  <div className="flex flex-col items-center gap-1 text-center">
                    <BookOpenIcon className="h-4 w-4 text-gray-400" />
                    <span className="text-sm font-semibold text-gray-900">
                      {(section as any).course_count ?? 0}
                    </span>
                    <span className="text-[11px] text-gray-500 leading-tight">
                      {((section as any).course_count ?? 0) === 1
                        ? 'Course'
                        : 'Courses'}
                    </span>
                  </div>
                </div>

                {/* Footer chevron */}
                <div className="mt-3 flex items-center justify-end">
                  <ChevronRightIcon className="h-4 w-4 text-gray-300 group-hover:text-primary-500 transition-colors" />
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── Add / Edit Section Modal ────────────────────────────────────── */}
      {showAddModal && (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center bg-black/50 p-0 sm:items-center sm:p-4"
          onClick={(e) => {
            if (e.target === e.currentTarget) closeModal();
          }}
        >
          <div className="max-h-[92vh] w-full max-w-md overflow-y-auto rounded-t-2xl bg-white p-5 pb-6 sm:rounded-xl sm:p-6 shadow-xl">
            {/* Modal header */}
            <div className="flex items-center justify-between mb-5">
              <h3 className="text-lg font-semibold text-gray-900">
                {editingSection ? 'Edit Section' : 'Add Section'}
              </h3>
              <button
                onClick={closeModal}
                className="text-gray-400 hover:text-gray-600 transition-colors"
                aria-label="Close modal"
              >
                <XMarkIcon className="h-6 w-6" />
              </button>
            </div>

            <form onSubmit={handleSubmitSection} noValidate className="space-y-4">
              {/* Section Name */}
              <div>
                <label
                  htmlFor="section-name"
                  className="block text-sm font-medium text-gray-700 mb-1"
                >
                  Section Name <span className="text-red-500">*</span>
                </label>
                <input
                  id="section-name"
                  type="text"
                  value={formData.name}
                  onChange={(e) => handleFormChange('name', e.target.value)}
                  placeholder='e.g. "A", "B", "C" or "Alpha", "Beta"'
                  className={`w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors ${
                    formErrors.name
                      ? 'border-red-300 focus:ring-red-500 focus:border-red-500'
                      : 'border-gray-300'
                  }`}
                  autoFocus
                />
                {formErrors.name ? (
                  <p className="mt-1 text-xs text-red-500">{formErrors.name}</p>
                ) : (
                  <p className="mt-1 text-xs text-gray-400">
                    Will display as &ldquo;{grade?.name ?? 'Grade'} -{' '}
                    {formData.name || '...'}&rdquo;
                  </p>
                )}
              </div>

              {/* Academic Year */}
              <div>
                <label
                  htmlFor="academic-year"
                  className="block text-sm font-medium text-gray-700 mb-1"
                >
                  Academic Year <span className="text-red-500">*</span>
                </label>
                <input
                  id="academic-year"
                  type="text"
                  value={formData.academic_year}
                  readOnly={!!gradeInfo?.academicYear}
                  onChange={(e) =>
                    handleFormChange('academic_year', e.target.value)
                  }
                  placeholder="e.g. 2025-2026"
                  className={`w-full px-3 py-2 border rounded-lg text-sm transition-colors ${
                    gradeInfo?.academicYear
                      ? 'border-gray-200 bg-gray-50 text-gray-600 cursor-not-allowed'
                      : formErrors.academic_year
                        ? 'border-red-300 focus:ring-red-500 focus:border-red-500 focus:outline-none focus:ring-2'
                        : 'border-gray-300 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500'
                  }`}
                />
                {formErrors.academic_year && (
                  <p className="mt-1 text-xs text-red-500">
                    {formErrors.academic_year}
                  </p>
                )}
                {gradeInfo?.academicYear && (
                  <p className="mt-1 text-xs text-gray-400">
                    Pre-filled from the current academic year
                  </p>
                )}
              </div>

              {/* Class Teacher (optional) */}
              <div>
                <label
                  htmlFor="class-teacher"
                  className="block text-sm font-medium text-gray-700 mb-1"
                >
                  Class Teacher{' '}
                  <span className="text-gray-400 font-normal">(optional)</span>
                </label>
                <input
                  id="class-teacher"
                  type="text"
                  value={formData.class_teacher ?? ''}
                  onChange={(e) =>
                    handleFormChange('class_teacher', e.target.value)
                  }
                  placeholder="Teacher name or ID"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors"
                />
                <p className="mt-1 text-xs text-gray-400">
                  Assign a class teacher to this section. Can be updated later.
                </p>
              </div>

              {/* Actions */}
              <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-end">
                <button
                  type="button"
                  onClick={closeModal}
                  className="w-full sm:w-auto px-4 py-2 text-sm font-medium rounded-lg border-2 border-gray-300 text-gray-700 hover:bg-gray-50 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isMutating}
                  className="w-full sm:w-auto inline-flex items-center justify-center px-4 py-2 text-sm font-medium rounded-lg bg-primary-600 hover:bg-primary-700 text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isMutating && <Spinner className="-ml-1 mr-2 h-4 w-4" />}
                  {editingSection ? 'Save Changes' : 'Create Section'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── Delete Section Confirmation ─────────────────────────────────── */}
      {deletingSection && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-md bg-white rounded-xl shadow-xl p-6">
            <div className="flex items-start gap-4">
              <div className="flex-shrink-0 p-2 rounded-full bg-red-100">
                <svg
                  className="h-6 w-6 text-red-600"
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
              <div className="flex-1 min-w-0">
                <h3 className="text-lg font-semibold text-gray-900">
                  Delete Section
                </h3>
                <p className="mt-2 text-sm text-gray-500">
                  Are you sure you want to delete{' '}
                  <strong>
                    {grade?.name} - {deletingSection.name}
                  </strong>
                  ?
                  {deletingSection.student_count > 0 && (
                    <>
                      {' '}
                      This section has{' '}
                      <strong>
                        {deletingSection.student_count} student
                        {deletingSection.student_count !== 1 ? 's' : ''}
                      </strong>{' '}
                      enrolled.
                    </>
                  )}{' '}
                  This action cannot be undone.
                </p>
              </div>
            </div>
            <div className="mt-6 flex justify-end gap-3">
              <button
                type="button"
                onClick={() => setDeletingSection(null)}
                disabled={deleteSectionMutation.isPending}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() =>
                  deleteSectionMutation.mutate(deletingSection.id)
                }
                disabled={deleteSectionMutation.isPending}
                className="inline-flex items-center px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-lg hover:bg-red-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {deleteSectionMutation.isPending && (
                  <Spinner className="-ml-1 mr-2 h-4 w-4" />
                )}
                Delete Section
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── CSV Import Modal ────────────────────────────────────────────── */}
      {showImportModal && (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center bg-black/50 p-0 sm:items-center sm:p-4"
          onClick={(e) => {
            if (e.target === e.currentTarget) {
              setShowImportModal(false);
              setImportFile(null);
              setImportSectionId('');
            }
          }}
        >
          <div className="max-h-[92vh] w-full max-w-lg overflow-y-auto rounded-t-2xl bg-white p-5 pb-6 sm:rounded-xl sm:p-6 shadow-xl">
            {/* Header */}
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-gray-900">
                Import Students
              </h3>
              <button
                onClick={() => {
                  setShowImportModal(false);
                  setImportFile(null);
                  setImportSectionId('');
                }}
                className="text-gray-400 hover:text-gray-600 transition-colors"
                aria-label="Close import modal"
              >
                <XMarkIcon className="h-6 w-6" />
              </button>
            </div>

            <div className="space-y-4">
              {/* Section selector */}
              <div>
                <label
                  htmlFor="import-section"
                  className="block text-sm font-medium text-gray-700 mb-1"
                >
                  Target Section <span className="text-red-500">*</span>
                </label>
                <select
                  id="import-section"
                  value={importSectionId}
                  onChange={(e) => setImportSectionId(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors"
                >
                  <option value="">Select a section...</option>
                  {sectionList.map((s) => (
                    <option key={s.id} value={s.id}>
                      {grade?.name} - {s.name} ({s.student_count} students)
                    </option>
                  ))}
                </select>
              </div>

              {/* File upload */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  CSV File <span className="text-red-500">*</span>
                </label>
                <div
                  onClick={() => fileInputRef.current?.click()}
                  className={`border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors ${
                    importFile
                      ? 'border-primary-300 bg-primary-50'
                      : 'border-gray-300 hover:border-gray-400 bg-gray-50'
                  }`}
                >
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".csv"
                    className="hidden"
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f) setImportFile(f);
                    }}
                  />
                  {importFile ? (
                    <div className="flex items-center justify-center gap-3">
                      <div className="h-10 w-10 rounded-lg bg-primary-100 flex items-center justify-center">
                        <ArrowUpTrayIcon className="h-5 w-5 text-primary-600" />
                      </div>
                      <div className="text-left">
                        <p className="text-sm font-medium text-gray-900">
                          {importFile.name}
                        </p>
                        <p className="text-xs text-gray-500">
                          {(importFile.size / 1024).toFixed(1)} KB
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          setImportFile(null);
                          if (fileInputRef.current)
                            fileInputRef.current.value = '';
                        }}
                        className="ml-2 p-1 text-gray-400 hover:text-gray-600 rounded"
                      >
                        <XMarkIcon className="h-4 w-4" />
                      </button>
                    </div>
                  ) : (
                    <>
                      <ArrowUpTrayIcon className="h-8 w-8 text-gray-400 mx-auto mb-2" />
                      <p className="text-sm text-gray-600">
                        Click to upload or drag &amp; drop
                      </p>
                      <p className="text-xs text-gray-400 mt-1">
                        CSV files only
                      </p>
                    </>
                  )}
                </div>
              </div>

              {/* CSV format hint */}
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-100">
                <p className="text-xs font-medium text-gray-600 mb-1">
                  Expected CSV columns:
                </p>
                <code className="text-xs text-gray-500">
                  email, first_name, last_name, parent_email (optional)
                </code>
              </div>

              {/* Import results (shown inline if there were errors) */}
              {importStudentsMutation.isSuccess &&
                importStudentsMutation.data.errors.length > 0 && (
                  <div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
                    <p className="text-sm font-medium text-amber-800 mb-2">
                      Import completed with{' '}
                      {importStudentsMutation.data.errors.length} error
                      {importStudentsMutation.data.errors.length !== 1
                        ? 's'
                        : ''}
                      :
                    </p>
                    <div className="max-h-32 overflow-y-auto space-y-1">
                      {importStudentsMutation.data.errors.map((err, i) => (
                        <p key={i} className="text-xs text-amber-700">
                          Row {err.row}: {err.error}
                        </p>
                      ))}
                    </div>
                  </div>
                )}

              {/* Actions */}
              <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-end">
                <button
                  type="button"
                  onClick={() => {
                    setShowImportModal(false);
                    setImportFile(null);
                    setImportSectionId('');
                  }}
                  className="w-full sm:w-auto px-4 py-2 text-sm font-medium rounded-lg border-2 border-gray-300 text-gray-700 hover:bg-gray-50 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleImportSubmit}
                  disabled={
                    !importFile ||
                    !importSectionId ||
                    importStudentsMutation.isPending
                  }
                  className="w-full sm:w-auto inline-flex items-center justify-center px-4 py-2 text-sm font-medium rounded-lg bg-primary-600 hover:bg-primary-700 text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {importStudentsMutation.isPending && (
                    <Spinner className="-ml-1 mr-2 h-4 w-4" />
                  )}
                  Import Students
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
