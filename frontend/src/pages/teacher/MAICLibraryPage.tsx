// src/pages/teacher/MAICLibraryPage.tsx
//
// Teacher AI Classroom library — grid of ClassroomCards with search + status filter.
// Includes section assignment modal for targeting classrooms to specific sections.

import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { usePageTitle } from '../../hooks/usePageTitle';
import { maicApi, chatbotApi } from '../../services/openmaicService';
import type { MAICClassroomMeta, MAICAssignedSection } from '../../types/maic';
import type { TeacherSection } from '../../types/chatbot';

// ─── Inline Icons ─────────────────────────────────────────────────────────────

const PlusIcon = () => (
  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
  </svg>
);

const SearchIcon = () => (
  <svg className="h-4 w-4 text-gray-400" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
  </svg>
);

const PresentationIcon = () => (
  <svg className="h-12 w-12 text-gray-300" fill="none" viewBox="0 0 24 24" strokeWidth={1} stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 3v11.25A2.25 2.25 0 0 0 6 16.5h2.25M3.75 3h16.5M3.75 3h-.375a1.125 1.125 0 0 1-1.125-1.125v0c0-.621.504-1.125 1.125-1.125H20.25c.621 0 1.125.504 1.125 1.125v0c0 .621-.504 1.125-1.125 1.125H20.25M3.75 3h16.5m0 0v11.25A2.25 2.25 0 0 1 18 16.5h-2.25m-7.5 0h7.5m-7.5 0-1 3m8.5-3 1 3m0 0 .5 1.5m-.5-1.5h-9.5m0 0-.5 1.5" />
  </svg>
);

const UsersIcon = () => (
  <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" d="M15 19.128a9.38 9.38 0 0 0 2.625.372 9.337 9.337 0 0 0 4.121-.952 4.125 4.125 0 0 0-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 0 1 8.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0 1 11.964-3.07M12 6.375a3.375 3.375 0 1 1-6.75 0 3.375 3.375 0 0 1 6.75 0Zm8.25 2.25a2.625 2.625 0 1 1-5.25 0 2.625 2.625 0 0 1 5.25 0Z" />
  </svg>
);

// ─── Status Badge ─────────────────────────────────────────────────────────────

const STATUS_STYLES: Record<string, string> = {
  DRAFT: 'bg-gray-100 text-gray-600',
  GENERATING: 'bg-amber-100 text-amber-700',
  READY: 'bg-green-100 text-green-700',
  FAILED: 'bg-red-100 text-red-600',
  ARCHIVED: 'bg-slate-100 text-slate-500',
};

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium ${STATUS_STYLES[status] || 'bg-gray-100 text-gray-600'}`}>
      {status}
    </span>
  );
}

// ─── Section Assignment Modal ─────────────────────────────────────────────────

function SectionAssignModal({
  classroom,
  availableSections,
  onClose,
  onSave,
  isSaving,
}: {
  classroom: MAICClassroomMeta;
  availableSections: TeacherSection[];
  onClose: () => void;
  onSave: (sectionIds: string[]) => void;
  isSaving: boolean;
}) {
  const [selected, setSelected] = useState<Set<string>>(() => {
    const ids = new Set<string>();
    (classroom.assigned_sections || []).forEach((s) => ids.add(s.id));
    return ids;
  });

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div
        className="bg-white rounded-xl shadow-xl w-full max-w-md mx-4 overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-6 py-4 border-b border-gray-200">
          <h3 className="text-base font-semibold text-gray-900">Assign Sections</h3>
          <p className="mt-1 text-xs text-gray-500">
            Choose which sections can access "{classroom.title}". Leave empty for all students.
          </p>
        </div>

        <div className="px-6 py-4 max-h-64 overflow-y-auto">
          {availableSections.length === 0 ? (
            <p className="text-sm text-gray-500 text-center py-4">
              No sections assigned to you. Contact your admin.
            </p>
          ) : (
            <div className="space-y-2">
              {availableSections.map((section) => (
                <label
                  key={section.id}
                  className={`flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                    selected.has(section.id)
                      ? 'border-indigo-300 bg-indigo-50'
                      : 'border-gray-200 hover:bg-gray-50'
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={selected.has(section.id)}
                    onChange={() => toggle(section.id)}
                    className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                  />
                  <div>
                    <span className="text-sm font-medium text-gray-900">{section.name}</span>
                    <span className="ml-2 text-xs text-gray-500">{section.grade_name}</span>
                  </div>
                </label>
              ))}
            </div>
          )}
        </div>

        <div className="px-6 py-4 border-t border-gray-200 flex items-center justify-between">
          <p className="text-xs text-gray-400">
            {selected.size === 0 ? 'All students (no restriction)' : `${selected.size} section${selected.size > 1 ? 's' : ''} selected`}
          </p>
          <div className="flex gap-2">
            <button
              onClick={onClose}
              className="px-3 py-1.5 text-sm text-gray-600 hover:text-gray-800"
            >
              Cancel
            </button>
            <button
              onClick={() => onSave(Array.from(selected))}
              disabled={isSaving}
              className="px-4 py-1.5 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 transition-colors"
            >
              {isSaving ? 'Saving...' : 'Save'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Classroom Card ───────────────────────────────────────────────────────────

const TrashIcon = () => (
  <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" />
  </svg>
);

function ClassroomCard({
  classroom,
  onClick,
  onAssignSections,
  onDelete,
}: {
  classroom: MAICClassroomMeta;
  onClick: () => void;
  onAssignSections: (e: React.MouseEvent) => void;
  onDelete: (e: React.MouseEvent) => void;
}) {
  const sections = classroom.assigned_sections || [];

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 hover:border-indigo-300 hover:shadow-md transition-all duration-150 group">
      <button onClick={onClick} className="text-left w-full">
        <div className="flex items-start justify-between mb-3">
          <h3 className="text-sm font-semibold text-gray-900 line-clamp-2 group-hover:text-indigo-700 transition-colors">
            {classroom.title}
          </h3>
          <StatusBadge status={classroom.status} />
        </div>

        {classroom.description && (
          <p className="text-xs text-gray-500 line-clamp-2 mb-3">{classroom.description}</p>
        )}

        <div className="flex items-center gap-3 text-[11px] text-gray-400 mb-3">
          <span>{classroom.scene_count} scenes</span>
          <span>{classroom.estimated_minutes} min</span>
          <span>{new Date(classroom.created_at).toLocaleDateString()}</span>
        </div>
      </button>

      {/* Section badges + assign button */}
      <div className="flex items-center gap-2 flex-wrap border-t border-gray-100 pt-3">
        {sections.length > 0 ? (
          sections.map((s) => (
            <span key={s.id} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 text-[10px] font-medium">
              {s.grade_name ? `${s.grade_name} - ${s.name}` : s.name}
            </span>
          ))
        ) : (
          <span className="text-[10px] text-gray-400">All students</span>
        )}
        <button
          onClick={onAssignSections}
          className="ml-auto inline-flex items-center gap-1 px-2 py-1 rounded-md text-[11px] text-gray-500 hover:text-indigo-600 hover:bg-indigo-50 transition-colors"
          title="Assign sections"
        >
          <UsersIcon />
          Assign
        </button>
        <button
          onClick={onDelete}
          className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-[11px] text-gray-500 hover:text-red-600 hover:bg-red-50 transition-colors"
          title="Delete classroom"
        >
          <TrashIcon />
        </button>
      </div>
    </div>
  );
}

// ─── Filter Types ─────────────────────────────────────────────────────────────

type StatusFilter = 'all' | 'DRAFT' | 'READY' | 'ARCHIVED';

const STATUS_OPTIONS: { value: StatusFilter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'DRAFT', label: 'Draft' },
  { value: 'READY', label: 'Ready' },
  { value: 'ARCHIVED', label: 'Archived' },
];

// ─── Main Component ───────────────────────────────────────────────────────────

export const MAICLibraryPage: React.FC = () => {
  usePageTitle('AI Classroom');
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [assigningClassroom, setAssigningClassroom] = useState<MAICClassroomMeta | null>(null);

  const { data: classrooms = [], isLoading } = useQuery({
    queryKey: ['maic-classrooms', statusFilter, search],
    queryFn: async () => {
      const params: Record<string, string> = {};
      if (statusFilter !== 'all') params.status = statusFilter;
      if (search.trim()) params.search = search.trim();
      const res = await maicApi.listClassrooms(params);
      return res.data;
    },
  });

  // Fetch teacher's sections (reuse chatbot endpoint)
  const { data: teacherSections = [] } = useQuery({
    queryKey: ['teacher-sections'],
    queryFn: async () => {
      const res = await chatbotApi.mySections();
      return res.data;
    },
    enabled: !!assigningClassroom,
  });

  const deleteMutation = useMutation({
    mutationFn: (classroomId: string) => maicApi.deleteClassroom(classroomId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['maic-classrooms'] });
    },
  });

  const handleDelete = (e: React.MouseEvent, classroom: MAICClassroomMeta) => {
    e.stopPropagation();
    if (window.confirm(`Delete "${classroom.title}"? This cannot be undone.`)) {
      deleteMutation.mutate(classroom.id);
    }
  };

  const assignMutation = useMutation({
    mutationFn: ({ classroomId, sectionIds }: { classroomId: string; sectionIds: string[] }) =>
      maicApi.updateClassroom(classroomId, { assigned_section_ids: sectionIds }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['maic-classrooms'] });
      setAssigningClassroom(null);
    },
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">AI Classroom</h1>
          <p className="mt-1 text-sm text-gray-500">
            Create and manage AI-powered interactive classrooms
          </p>
        </div>
        <button
          onClick={() => navigate('/teacher/ai-classroom/new')}
          className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 transition-colors shadow-sm"
        >
          <PlusIcon />
          New Classroom
        </button>
      </div>

      {/* Filters */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1 max-w-sm">
          <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
            <SearchIcon />
          </div>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search classrooms..."
            className="w-full pl-9 pr-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-indigo-500 focus:border-indigo-500"
          />
        </div>

        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
          className="px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-indigo-500 focus:border-indigo-500"
        >
          {STATUS_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      {/* Grid */}
      {isLoading ? (
        <div className="flex justify-center py-16">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600" />
        </div>
      ) : classrooms.length === 0 ? (
        <div className="text-center py-16">
          <PresentationIcon />
          <h3 className="mt-4 text-lg font-medium text-gray-900">No classrooms yet</h3>
          <p className="mt-2 text-sm text-gray-500">
            Create your first AI Classroom to get started with interactive presentations.
          </p>
          <button
            onClick={() => navigate('/teacher/ai-classroom/new')}
            className="mt-6 inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 transition-colors"
          >
            <PlusIcon />
            Create Classroom
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {classrooms.map((c) => (
            <ClassroomCard
              key={c.id}
              classroom={c}
              onClick={() => navigate(`/teacher/ai-classroom/${c.id}`)}
              onAssignSections={(e) => {
                e.stopPropagation();
                setAssigningClassroom(c);
              }}
              onDelete={(e) => handleDelete(e, c)}
            />
          ))}
        </div>
      )}

      {/* Section Assignment Modal */}
      {assigningClassroom && (
        <SectionAssignModal
          classroom={assigningClassroom}
          availableSections={teacherSections}
          onClose={() => setAssigningClassroom(null)}
          onSave={(sectionIds) =>
            assignMutation.mutate({ classroomId: assigningClassroom.id, sectionIds })
          }
          isSaving={assignMutation.isPending}
        />
      )}
    </div>
  );
};
