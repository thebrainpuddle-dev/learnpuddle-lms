// src/pages/teacher/MAICLibraryPage.tsx
//
// Teacher AI Classroom library — grid of ClassroomCards with search + status filter.

import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { usePageTitle } from '../../hooks/usePageTitle';
import { maicApi } from '../../services/openmaicService';
import type { MAICClassroomMeta } from '../../types/maic';

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

// ─── Classroom Card ───────────────────────────────────────────────────────────

function ClassroomCard({ classroom, onClick }: { classroom: MAICClassroomMeta; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="text-left w-full bg-white rounded-xl border border-gray-200 p-5 hover:border-indigo-300 hover:shadow-md transition-all duration-150 group"
    >
      <div className="flex items-start justify-between mb-3">
        <h3 className="text-sm font-semibold text-gray-900 line-clamp-2 group-hover:text-indigo-700 transition-colors">
          {classroom.title}
        </h3>
        <StatusBadge status={classroom.status} />
      </div>

      {classroom.description && (
        <p className="text-xs text-gray-500 line-clamp-2 mb-3">{classroom.description}</p>
      )}

      <div className="flex items-center gap-3 text-[11px] text-gray-400">
        <span>{classroom.scene_count} scenes</span>
        <span>{classroom.estimated_minutes} min</span>
        <span>{new Date(classroom.created_at).toLocaleDateString()}</span>
      </div>
    </button>
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

  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');

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
            />
          ))}
        </div>
      )}
    </div>
  );
};
