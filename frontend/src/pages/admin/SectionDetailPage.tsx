// src/pages/admin/SectionDetailPage.tsx
//
// Admin Level 3 view: Section detail with Students, Teachers, and Courses tabs.
// URL: /admin/school/section/:sectionId?tab=students|teachers|courses

import React, { useState, useRef, useEffect, useMemo } from 'react';
import { useNavigate, useParams, useSearchParams, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeftIcon,
  UsersIcon,
  UserGroupIcon,
  BookOpenIcon,
  PlusIcon,
  ArrowUpTrayIcon,
  MagnifyingGlassIcon,
  CheckCircleIcon,
  XCircleIcon,
  ChevronRightIcon,
  XMarkIcon,
  AcademicCapIcon,
} from '@heroicons/react/24/outline';
import { usePageTitle } from '../../hooks/usePageTitle';
import { useToast } from '../../components/common';
import {
  academicsService,
  type SectionStudentsResponse,
  type SectionTeachersResponse,
  type SectionCoursesResponse,
  type CSVImportResult,
} from '../../services/academicsService';

// ─── Types ───────────────────────────────────────────────────────────────────

type TabKey = 'students' | 'teachers' | 'courses';

interface AddStudentFormData {
  first_name: string;
  last_name: string;
  email: string;
}

interface FormErrors {
  first_name?: string;
  last_name?: string;
  email?: string;
}

const TABS: { key: TabKey; label: string; icon: React.ElementType }[] = [
  { key: 'students', label: 'Students', icon: UserGroupIcon },
  { key: 'teachers', label: 'Teachers', icon: AcademicCapIcon },
  { key: 'courses', label: 'Courses', icon: BookOpenIcon },
];

const EMPTY_FORM: AddStudentFormData = {
  first_name: '',
  last_name: '',
  email: '',
};

// ─── Debounce hook ───────────────────────────────────────────────────────────

function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);
  useEffect(() => {
    const handler = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(handler);
  }, [value, delay]);
  return debouncedValue;
}

// ─── Spinner ─────────────────────────────────────────────────────────────────

const Spinner: React.FC<{ className?: string }> = ({ className = 'h-4 w-4' }) => (
  <svg className={`animate-spin ${className}`} viewBox="0 0 24 24" fill="none">
    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
    <path
      className="opacity-75"
      fill="currentColor"
      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
    />
  </svg>
);

// ─── Component ───────────────────────────────────────────────────────────────

export const SectionDetailPage: React.FC = () => {
  const { sectionId } = useParams<{ sectionId: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const toast = useToast();
  const queryClient = useQueryClient();
  const csvInputRef = useRef<HTMLInputElement>(null);

  // ─── Tab state from URL ──────────────────────────────────────────────────

  const activeTab = (searchParams.get('tab') as TabKey) || 'students';

  const setTab = (tab: TabKey) => {
    setSearchParams({ tab }, { replace: true });
    setStudentSearch('');
  };

  // ─── Local state ─────────────────────────────────────────────────────────

  const [studentSearch, setStudentSearch] = useState('');
  const debouncedSearch = useDebounce(studentSearch, 300);

  const [showAddModal, setShowAddModal] = useState(false);
  const [addForm, setAddForm] = useState<AddStudentFormData>(EMPTY_FORM);
  const [formErrors, setFormErrors] = useState<FormErrors>({});

  const [importResult, setImportResult] = useState<CSVImportResult | null>(null);

  // ─── Page title ──────────────────────────────────────────────────────────

  usePageTitle('Section Detail');

  // ─── Queries ─────────────────────────────────────────────────────────────

  const {
    data: studentsData,
    isLoading: studentsLoading,
    isError: studentsError,
  } = useQuery<SectionStudentsResponse>({
    queryKey: ['sectionStudents', sectionId, debouncedSearch],
    queryFn: () =>
      academicsService.getSectionStudents(sectionId!, debouncedSearch || undefined),
    enabled: !!sectionId && activeTab === 'students',
  });

  const {
    data: teachersData,
    isLoading: teachersLoading,
    isError: teachersError,
  } = useQuery<SectionTeachersResponse>({
    queryKey: ['sectionTeachers', sectionId],
    queryFn: () => academicsService.getSectionTeachers(sectionId!),
    enabled: !!sectionId && activeTab === 'teachers',
  });

  const {
    data: coursesData,
    isLoading: coursesLoading,
    isError: coursesError,
  } = useQuery<SectionCoursesResponse>({
    queryKey: ['sectionCourses', sectionId],
    queryFn: () => academicsService.getSectionCourses(sectionId!),
    enabled: !!sectionId && activeTab === 'courses',
  });

  // Section info from whichever query loaded first
  const sectionInfo =
    studentsData?.section ?? teachersData?.section ?? coursesData?.section;
  const gradeName = sectionInfo?.grade_name ?? 'Grade';
  const sectionName = sectionInfo?.name ?? 'Section';
  const academicYear = sectionInfo?.academic_year ?? '';

  // ─── Mutations ───────────────────────────────────────────────────────────

  const addStudentMut = useMutation({
    mutationFn: (data: { first_name: string; last_name: string; email: string }) =>
      academicsService.addStudent(sectionId!, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sectionStudents', sectionId] });
      toast.success('Student added', 'The student has been added to this section.');
      closeAddModal();
    },
    onError: (err: any) => {
      const detail = err?.response?.data;
      if (detail && typeof detail === 'object') {
        const serverErrors: FormErrors = {};
        for (const [field, messages] of Object.entries(detail)) {
          if (field in EMPTY_FORM) {
            (serverErrors as any)[field] = Array.isArray(messages)
              ? (messages as string[])[0]
              : String(messages);
          }
        }
        setFormErrors(serverErrors);
      }
      toast.error(
        'Failed to add student',
        detail?.detail ?? detail?.error ?? 'Please check the form and try again.',
      );
    },
  });

  const importStudentsMut = useMutation({
    mutationFn: (file: File) => academicsService.importStudents(sectionId!, file),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['sectionStudents', sectionId] });
      setImportResult(data);
      toast.success(
        'Import complete',
        `${data.created} of ${data.total_rows} students imported successfully.`,
      );
    },
    onError: () => {
      toast.error('Import failed', 'Check your CSV format and try again.');
    },
  });

  // ─── Form validation ────────────────────────────────────────────────────

  const validateForm = (): boolean => {
    const errors: FormErrors = {};
    if (!addForm.first_name.trim()) errors.first_name = 'First name is required';
    if (!addForm.last_name.trim()) errors.last_name = 'Last name is required';
    if (!addForm.email.trim()) {
      errors.email = 'Email is required';
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(addForm.email)) {
      errors.email = 'Enter a valid email address';
    }
    setFormErrors(errors);
    return Object.keys(errors).length === 0;
  };

  // ─── Modal helpers ───────────────────────────────────────────────────────

  const closeAddModal = () => {
    setShowAddModal(false);
    setAddForm(EMPTY_FORM);
    setFormErrors({});
  };

  const handleAddSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!validateForm()) return;
    addStudentMut.mutate({
      first_name: addForm.first_name.trim(),
      last_name: addForm.last_name.trim(),
      email: addForm.email.trim(),
    });
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setImportResult(null);
      importStudentsMut.mutate(file);
    }
    // Reset so the same file can be re-selected
    if (csvInputRef.current) csvInputRef.current.value = '';
  };

  // ─── Formatting helpers ──────────────────────────────────────────────────

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '---';
    return new Date(dateStr).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  };

  const formatDateTime = (dateStr: string | null) => {
    if (!dateStr) return 'Never';
    return new Date(dateStr).toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    });
  };

  // ─── Shared render helpers ───────────────────────────────────────────────

  const renderLoadingState = () => (
    <div className="flex items-center justify-center py-16">
      <div className="flex flex-col items-center">
        <Spinner className="h-10 w-10 text-primary-600" />
        <p className="mt-4 text-sm text-gray-500">Loading...</p>
      </div>
    </div>
  );

  const renderErrorState = (message: string) => (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <XCircleIcon className="h-12 w-12 text-red-400" />
      <p className="mt-3 text-sm text-gray-600">{message}</p>
      <button
        onClick={() =>
          queryClient.invalidateQueries({
            queryKey: [
              activeTab === 'students'
                ? 'sectionStudents'
                : activeTab === 'teachers'
                  ? 'sectionTeachers'
                  : 'sectionCourses',
              sectionId,
            ],
          })
        }
        className="mt-4 text-sm font-medium text-primary-600 hover:text-primary-700"
      >
        Try again
      </button>
    </div>
  );

  const renderEmptyState = (
    icon: React.ElementType,
    title: string,
    description: string,
    action?: React.ReactNode,
  ) => {
    const Icon = icon;
    return (
      <div className="rounded-xl border border-gray-200 bg-white p-12 text-center">
        <Icon className="mx-auto h-12 w-12 text-gray-300" />
        <h3 className="mt-3 text-sm font-semibold text-gray-900">{title}</h3>
        <p className="mt-1 text-sm text-gray-500">{description}</p>
        {action && <div className="mt-6 flex items-center justify-center gap-3">{action}</div>}
      </div>
    );
  };

  // ─── Students Tab ────────────────────────────────────────────────────────

  const renderStudentsTab = () => {
    if (studentsLoading) return renderLoadingState();
    if (studentsError)
      return renderErrorState('Failed to load students. Please try again.');

    const students = studentsData?.students ?? [];

    return (
      <div className="space-y-4">
        {/* Toolbar: search + actions */}
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          {/* Search bar */}
          <div className="relative flex-1 max-w-md">
            <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400" />
            <input
              type="text"
              placeholder="Search students by name, email, or ID..."
              value={studentSearch}
              onChange={(e) => setStudentSearch(e.target.value)}
              className="w-full pl-10 pr-10 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
            />
            {studentSearch && (
              <button
                onClick={() => setStudentSearch('')}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
              >
                <XMarkIcon className="h-4 w-4" />
              </button>
            )}
          </div>

          {/* Action buttons */}
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowAddModal(true)}
              className="inline-flex items-center gap-1.5 rounded-lg bg-primary-600 px-4 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-primary-700 transition"
            >
              <PlusIcon className="h-4 w-4" />
              Add Student
            </button>
            <button
              onClick={() => csvInputRef.current?.click()}
              disabled={importStudentsMut.isPending}
              className="inline-flex items-center gap-1.5 rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm font-medium text-gray-700 shadow-sm hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition"
            >
              <ArrowUpTrayIcon className="h-4 w-4" />
              {importStudentsMut.isPending ? 'Importing...' : 'Import CSV'}
            </button>
            {/* Hidden file input for CSV */}
            <input
              ref={csvInputRef}
              type="file"
              accept=".csv,text/csv"
              onChange={handleFileSelect}
              className="hidden"
            />
          </div>
        </div>

        {/* CSV import results banner */}
        {importResult && (
          <div className="rounded-lg border border-gray-200 bg-white shadow-sm">
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
              <h4 className="text-sm font-semibold text-gray-900">Import Results</h4>
              <button
                onClick={() => setImportResult(null)}
                className="text-gray-400 hover:text-gray-600"
              >
                <XMarkIcon className="h-4 w-4" />
              </button>
            </div>
            <div className="grid grid-cols-3 divide-x divide-gray-100">
              <div className="px-4 py-3 text-center">
                <p className="text-2xl font-bold text-green-600">{importResult.created}</p>
                <p className="text-xs text-gray-500">Created</p>
              </div>
              <div className="px-4 py-3 text-center">
                <p className="text-2xl font-bold text-amber-600">{importResult.skipped}</p>
                <p className="text-xs text-gray-500">Skipped</p>
              </div>
              <div className="px-4 py-3 text-center">
                <p className="text-2xl font-bold text-gray-600">{importResult.total_rows}</p>
                <p className="text-xs text-gray-500">Total Rows</p>
              </div>
            </div>
            {importResult.errors.length > 0 && (
              <div className="border-t border-gray-100 px-4 py-3">
                <p className="text-xs font-medium text-red-700 mb-2">
                  {importResult.errors.length} error
                  {importResult.errors.length !== 1 ? 's' : ''} found:
                </p>
                <div className="max-h-32 overflow-y-auto space-y-1">
                  {importResult.errors.map((err, idx) => (
                    <div key={idx} className="flex items-start gap-2 text-xs text-red-600">
                      <XCircleIcon className="h-3.5 w-3.5 flex-shrink-0 mt-0.5" />
                      <span>
                        Row {err.row}: {err.error}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Students table */}
        {students.length === 0 ? (
          renderEmptyState(
            UserGroupIcon,
            'No students found',
            debouncedSearch
              ? 'No students match your search criteria.'
              : 'Get started by adding students to this section.',
            !debouncedSearch ? (
              <>
                <button
                  onClick={() => setShowAddModal(true)}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 transition"
                >
                  <PlusIcon className="h-4 w-4" />
                  Add Student
                </button>
                <button
                  onClick={() => csvInputRef.current?.click()}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 transition"
                >
                  <ArrowUpTrayIcon className="h-4 w-4" />
                  Import CSV
                </button>
              </>
            ) : undefined,
          )
        ) : (
          <div className="overflow-x-auto bg-white rounded-xl border border-gray-200 shadow-sm">
            <table className="min-w-full divide-y divide-gray-200 text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Name
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Student ID
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider hidden sm:table-cell">
                    Email
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Status
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider hidden md:table-cell">
                    Last Login
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {students.map((student) => (
                  <tr key={student.id} className="hover:bg-gray-50 transition-colors">
                    <td className="px-4 py-3 whitespace-nowrap">
                      <div className="flex items-center gap-3">
                        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary-100 text-primary-700 text-xs font-semibold">
                          {student.first_name?.[0]?.toUpperCase() ?? ''}
                          {student.last_name?.[0]?.toUpperCase() ?? ''}
                        </div>
                        <div>
                          <p className="font-medium text-gray-900">
                            {student.first_name} {student.last_name}
                          </p>
                          <p className="text-xs text-gray-500 sm:hidden">{student.email}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-gray-600 font-mono text-xs">
                      {student.student_id || '---'}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-gray-600 hidden sm:table-cell">
                      {student.email}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      {student.is_active ? (
                        <span className="inline-flex items-center gap-1 rounded-full bg-green-50 px-2.5 py-0.5 text-xs font-medium text-green-700">
                          <CheckCircleIcon className="h-3.5 w-3.5" />
                          Active
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 rounded-full bg-red-50 px-2.5 py-0.5 text-xs font-medium text-red-700">
                          <XCircleIcon className="h-3.5 w-3.5" />
                          Inactive
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-gray-500 text-xs hidden md:table-cell">
                      {formatDateTime(student.last_login)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {/* Footer count */}
            <div className="border-t border-gray-200 bg-gray-50 px-4 py-2.5 text-xs text-gray-500">
              {studentsData?.total ?? students.length} student
              {(studentsData?.total ?? students.length) !== 1 ? 's' : ''} total
              {debouncedSearch && ' (filtered)'}
            </div>
          </div>
        )}
      </div>
    );
  };

  // ─── Teachers Tab ────────────────────────────────────────────────────────

  const renderTeachersTab = () => {
    if (teachersLoading) return renderLoadingState();
    if (teachersError)
      return renderErrorState('Failed to load teachers. Please try again.');

    const teachers = teachersData?.teachers ?? [];

    if (teachers.length === 0) {
      return renderEmptyState(
        AcademicCapIcon,
        'No teachers assigned',
        'Teaching assignments for this section are managed from the Teaching Assignments page.',
      );
    }

    return (
      <div className="space-y-4">
        <p className="text-sm text-gray-500">
          Teachers assigned to this section via Teaching Assignments. To modify, go to
          the Teaching Assignments page.
        </p>
        <div className="overflow-x-auto bg-white rounded-xl border border-gray-200 shadow-sm">
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Teacher Name
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Subject
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider hidden sm:table-cell">
                  Email
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Role
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {teachers.map((assignment) => (
                <tr key={assignment.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3 whitespace-nowrap">
                    <div className="flex items-center gap-3">
                      <div className="flex h-8 w-8 items-center justify-center rounded-full bg-indigo-100 text-indigo-700 text-xs font-semibold">
                        {assignment.teacher_name?.[0]?.toUpperCase() ?? 'T'}
                      </div>
                      <div>
                        <p className="font-medium text-gray-900">
                          {assignment.teacher_name}
                        </p>
                        <p className="text-xs text-gray-500 sm:hidden">
                          {assignment.teacher_email}
                        </p>
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    <div>
                      <p className="font-medium text-gray-900">
                        {assignment.subject_name}
                      </p>
                      <p className="text-xs text-gray-500">{assignment.subject_code}</p>
                    </div>
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap text-gray-600 hidden sm:table-cell">
                    {assignment.teacher_email}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    {assignment.is_class_teacher ? (
                      <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2.5 py-0.5 text-xs font-medium text-amber-700 ring-1 ring-inset ring-amber-600/20">
                        <AcademicCapIcon className="h-3.5 w-3.5" />
                        Class Teacher
                      </span>
                    ) : (
                      <span className="text-xs text-gray-500">Subject Teacher</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="border-t border-gray-200 bg-gray-50 px-4 py-2.5 text-xs text-gray-500">
            {teachers.length} assignment{teachers.length !== 1 ? 's' : ''}
          </div>
        </div>
      </div>
    );
  };

  // ─── Courses Tab ─────────────────────────────────────────────────────────

  const renderCoursesTab = () => {
    if (coursesLoading) return renderLoadingState();
    if (coursesError)
      return renderErrorState('Failed to load courses. Please try again.');

    const courses = coursesData?.courses ?? [];

    if (courses.length === 0) {
      return renderEmptyState(
        BookOpenIcon,
        'No courses assigned',
        'Courses targeting this section will appear here once they are created.',
        <button
          onClick={() => navigate('/admin/courses/new')}
          className="inline-flex items-center gap-1.5 rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 transition"
        >
          <BookOpenIcon className="h-4 w-4" />
          Create Course
        </button>,
      );
    }

    return (
      <div className="overflow-x-auto bg-white rounded-xl border border-gray-200 shadow-sm">
        <table className="min-w-full divide-y divide-gray-200 text-sm">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Course Title
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Published
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Active
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider hidden sm:table-cell">
                Created
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider hidden md:table-cell">
                Students
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {courses.map((course) => (
              <tr
                key={course.id}
                onClick={() => navigate(`/admin/courses/${course.id}/edit`)}
                className="hover:bg-gray-50 transition-colors cursor-pointer"
              >
                <td className="px-4 py-3 whitespace-nowrap">
                  <p className="font-medium text-gray-900 hover:text-primary-700 transition-colors">
                    {course.title}
                  </p>
                </td>
                <td className="px-4 py-3 whitespace-nowrap">
                  {course.is_published ? (
                    <span className="inline-flex items-center gap-1 rounded-full bg-green-50 px-2.5 py-0.5 text-xs font-medium text-green-700 ring-1 ring-inset ring-green-600/20">
                      <CheckCircleIcon className="h-3 w-3" />
                      Published
                    </span>
                  ) : (
                    <span className="inline-flex items-center rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-medium text-gray-600 ring-1 ring-inset ring-gray-500/10">
                      Draft
                    </span>
                  )}
                </td>
                <td className="px-4 py-3 whitespace-nowrap">
                  {course.is_active ? (
                    <span className="inline-flex items-center gap-1 rounded-full bg-blue-50 px-2.5 py-0.5 text-xs font-medium text-blue-700 ring-1 ring-inset ring-blue-600/20">
                      Active
                    </span>
                  ) : (
                    <span className="inline-flex items-center rounded-full bg-red-50 px-2.5 py-0.5 text-xs font-medium text-red-700 ring-1 ring-inset ring-red-600/10">
                      Inactive
                    </span>
                  )}
                </td>
                <td className="px-4 py-3 whitespace-nowrap text-gray-500 text-xs hidden sm:table-cell">
                  {formatDate(course.created_at)}
                </td>
                <td className="px-4 py-3 whitespace-nowrap text-gray-600 text-xs hidden md:table-cell">
                  {course.student_count !== undefined ? (
                    <span className="flex items-center gap-1">
                      <UserGroupIcon className="h-3.5 w-3.5 text-gray-400" />
                      {course.student_count}
                    </span>
                  ) : (
                    '---'
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="border-t border-gray-200 bg-gray-50 px-4 py-2.5 text-xs text-gray-500">
          {courses.length} course{courses.length !== 1 ? 's' : ''}
        </div>
      </div>
    );
  };

  // ─── Add Student Modal ───────────────────────────────────────────────────

  const renderAddStudentModal = () => {
    if (!showAddModal) return null;

    return (
      <div className="fixed inset-0 z-50 overflow-y-auto">
        <div className="flex min-h-full items-center justify-center p-4">
          {/* Backdrop */}
          <div
            className="fixed inset-0 bg-gray-500/75 transition-opacity"
            onClick={closeAddModal}
            aria-hidden="true"
          />

          {/* Modal panel */}
          <div className="relative w-full max-w-md transform rounded-xl bg-white shadow-xl transition-all">
            {/* Header */}
            <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
              <div>
                <h2 className="text-lg font-semibold text-gray-900">Add Student</h2>
                <p className="mt-0.5 text-sm text-gray-500">
                  Add a new student to {gradeName} - {sectionName}
                </p>
              </div>
              <button
                onClick={closeAddModal}
                className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600 transition"
              >
                <XMarkIcon className="h-5 w-5" />
              </button>
            </div>

            {/* Form */}
            <form onSubmit={handleAddSubmit}>
              <div className="space-y-4 px-6 py-5">
                {/* First Name */}
                <div>
                  <label
                    htmlFor="add-first-name"
                    className="block text-sm font-medium text-gray-700 mb-1"
                  >
                    First Name <span className="text-red-500">*</span>
                  </label>
                  <input
                    id="add-first-name"
                    type="text"
                    value={addForm.first_name}
                    onChange={(e) => {
                      setAddForm((prev) => ({ ...prev, first_name: e.target.value }));
                      if (formErrors.first_name)
                        setFormErrors((prev) => ({ ...prev, first_name: undefined }));
                    }}
                    className={`w-full rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 ${
                      formErrors.first_name
                        ? 'border-red-400 focus:ring-red-500'
                        : 'border-gray-300'
                    }`}
                    placeholder="Enter first name"
                    autoFocus
                  />
                  {formErrors.first_name && (
                    <p className="mt-1 text-xs text-red-600">{formErrors.first_name}</p>
                  )}
                </div>

                {/* Last Name */}
                <div>
                  <label
                    htmlFor="add-last-name"
                    className="block text-sm font-medium text-gray-700 mb-1"
                  >
                    Last Name <span className="text-red-500">*</span>
                  </label>
                  <input
                    id="add-last-name"
                    type="text"
                    value={addForm.last_name}
                    onChange={(e) => {
                      setAddForm((prev) => ({ ...prev, last_name: e.target.value }));
                      if (formErrors.last_name)
                        setFormErrors((prev) => ({ ...prev, last_name: undefined }));
                    }}
                    className={`w-full rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 ${
                      formErrors.last_name
                        ? 'border-red-400 focus:ring-red-500'
                        : 'border-gray-300'
                    }`}
                    placeholder="Enter last name"
                  />
                  {formErrors.last_name && (
                    <p className="mt-1 text-xs text-red-600">{formErrors.last_name}</p>
                  )}
                </div>

                {/* Email */}
                <div>
                  <label
                    htmlFor="add-email"
                    className="block text-sm font-medium text-gray-700 mb-1"
                  >
                    Email <span className="text-red-500">*</span>
                  </label>
                  <input
                    id="add-email"
                    type="email"
                    value={addForm.email}
                    onChange={(e) => {
                      setAddForm((prev) => ({ ...prev, email: e.target.value }));
                      if (formErrors.email)
                        setFormErrors((prev) => ({ ...prev, email: undefined }));
                    }}
                    className={`w-full rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 ${
                      formErrors.email
                        ? 'border-red-400 focus:ring-red-500'
                        : 'border-gray-300'
                    }`}
                    placeholder="student@school.edu"
                  />
                  {formErrors.email && (
                    <p className="mt-1 text-xs text-red-600">{formErrors.email}</p>
                  )}
                </div>
              </div>

              {/* Footer */}
              <div className="flex items-center justify-end gap-3 border-t border-gray-200 px-6 py-4">
                <button
                  type="button"
                  onClick={closeAddModal}
                  className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={addStudentMut.isPending}
                  className="inline-flex items-center gap-2 rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition"
                >
                  {addStudentMut.isPending && <Spinner />}
                  Add Student
                </button>
              </div>
            </form>
          </div>
        </div>
      </div>
    );
  };

  // ─── Main Render ─────────────────────────────────────────────────────────

  return (
    <div className="space-y-6">
      {/* Breadcrumb */}
      <nav className="flex items-center gap-1.5 text-sm text-gray-500" aria-label="Breadcrumb">
        <Link to="/admin/school" className="hover:text-primary-600 transition-colors">
          School
        </Link>
        <ChevronRightIcon className="h-3.5 w-3.5 flex-shrink-0" />
        {sectionInfo?.grade && (
          <>
            <Link
              to={`/admin/school/grade/${sectionInfo.grade}`}
              className="hover:text-primary-600 transition-colors"
            >
              {gradeName}
            </Link>
            <ChevronRightIcon className="h-3.5 w-3.5 flex-shrink-0" />
          </>
        )}
        <span className="font-medium text-gray-900">{sectionName}</span>
      </nav>

      {/* Section info bar */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex items-start gap-3">
          <button
            onClick={() =>
              navigate(
                sectionInfo?.grade
                  ? `/admin/school/${sectionInfo.grade}`
                  : '/admin/school',
              )
            }
            className="mt-1 rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600 transition"
            title="Back to grade"
          >
            <ArrowLeftIcon className="h-5 w-5" />
          </button>
          <div>
            <div className="flex items-center gap-3 flex-wrap">
              <h1 className="text-2xl font-bold text-gray-900">
                {gradeName} - {sectionName}
              </h1>
              {academicYear && (
                <span className="inline-flex items-center rounded-full bg-indigo-50 px-2.5 py-0.5 text-xs font-medium text-indigo-700 ring-1 ring-inset ring-indigo-700/10">
                  {academicYear}
                </span>
              )}
            </div>
            <p className="mt-1 text-sm text-gray-500">
              {sectionInfo?.class_teacher_name
                ? `Class Teacher: ${sectionInfo.class_teacher_name}`
                : 'No class teacher assigned'}
              {' | '}
              {sectionInfo?.student_count ?? 0} student
              {(sectionInfo?.student_count ?? 0) !== 1 ? 's' : ''}
            </p>
          </div>
        </div>
      </div>

      {/* Tab bar */}
      <div className="border-b border-gray-200">
        <nav className="flex gap-6" aria-label="Section tabs">
          {TABS.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.key;
            return (
              <button
                key={tab.key}
                onClick={() => setTab(tab.key)}
                className={`inline-flex items-center gap-2 border-b-2 py-2.5 text-sm font-medium transition ${
                  isActive
                    ? 'border-primary-600 text-primary-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
                aria-current={isActive ? 'page' : undefined}
              >
                <Icon className="h-4 w-4" />
                {tab.label}
              </button>
            );
          })}
        </nav>
      </div>

      {/* Tab content */}
      <div>
        {activeTab === 'students' && renderStudentsTab()}
        {activeTab === 'teachers' && renderTeachersTab()}
        {activeTab === 'courses' && renderCoursesTab()}
      </div>

      {/* Modal */}
      {renderAddStudentModal()}
    </div>
  );
};
