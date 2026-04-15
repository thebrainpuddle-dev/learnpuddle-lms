// src/pages/student/MAICBrowsePage.tsx
//
// Student AI Classroom page — two tabs: Browse (teacher classrooms) + My Classrooms.
// Students can create their own AI classrooms with guardrail validation.

import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { usePageTitle } from '../../hooks/usePageTitle';
import { maicStudentApi } from '../../services/openmaicService';
import { deleteStoredClassroom } from '../../lib/maicDb';
import type { MAICClassroomMeta } from '../../types/maic';
import { cn } from '../../lib/utils';

// ─── Inline Icons ─────────────────────────────────────────────────────────────

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

const PlusIcon = () => (
  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
  </svg>
);

const TrashIcon = () => (
  <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" />
  </svg>
);

// ─── Classroom Card ───────────────────────────────────────────────────────────

function ClassroomCard({ classroom, onClick }: { classroom: MAICClassroomMeta; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="text-left w-full bg-white rounded-xl border border-gray-200 p-5 hover:border-indigo-300 hover:shadow-md transition-all duration-150 group"
    >
      <h3 className="text-sm font-semibold text-gray-900 line-clamp-2 group-hover:text-indigo-700 transition-colors mb-2">
        {classroom.title}
      </h3>

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

const STATUS_BADGE: Record<string, { label: string; color: string }> = {
  DRAFT: { label: 'Draft', color: 'bg-gray-100 text-gray-600' },
  GENERATING: { label: 'Generating...', color: 'bg-amber-100 text-amber-700' },
  READY: { label: 'Ready', color: 'bg-green-100 text-green-700' },
  FAILED: { label: 'Failed', color: 'bg-red-100 text-red-700' },
};

function MyClassroomCard({
  classroom, onClick, onDelete,
}: {
  classroom: MAICClassroomMeta;
  onClick: () => void;
  onDelete: () => void;
}) {
  const badge = STATUS_BADGE[classroom.status] || STATUS_BADGE.DRAFT;

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 hover:border-indigo-300 hover:shadow-md transition-all duration-150 group">
      <div className="flex items-start justify-between mb-2">
        <button
          onClick={onClick}
          className="text-left flex-1 min-w-0"
        >
          <h3 className="text-sm font-semibold text-gray-900 line-clamp-2 group-hover:text-indigo-700 transition-colors">
            {classroom.title}
          </h3>
        </button>
        <span className={cn('shrink-0 ml-2 text-[10px] font-medium px-2 py-0.5 rounded-full', badge.color)}>
          {badge.label}
        </span>
      </div>

      <div className="flex items-center justify-between mt-3">
        <div className="flex items-center gap-3 text-[11px] text-gray-400">
          {classroom.scene_count > 0 && <span>{classroom.scene_count} scenes</span>}
          <span>{new Date(classroom.created_at).toLocaleDateString()}</span>
        </div>
        <button
          onClick={(e) => { e.stopPropagation(); onDelete(); }}
          className="p-1 rounded text-gray-300 hover:text-red-500 hover:bg-red-50 transition-colors"
          title="Delete classroom"
        >
          <TrashIcon />
        </button>
      </div>
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────

type Tab = 'browse' | 'mine';

export const MAICBrowsePage: React.FC = () => {
  usePageTitle('AI Classroom');
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [tab, setTab] = useState<Tab>('browse');
  const [search, setSearch] = useState('');

  // Browse classrooms (teacher-created public)
  const { data: classrooms = [], isLoading: isLoadingBrowse } = useQuery({
    queryKey: ['student-maic-classrooms', search],
    queryFn: async () => {
      const params: Record<string, string> = {};
      if (search.trim()) params.search = search.trim();
      const res = await maicStudentApi.listClassrooms(params);
      return res.data;
    },
    enabled: tab === 'browse',
  });

  // My classrooms (student-created)
  const { data: myClassrooms = [], isLoading: isLoadingMine } = useQuery({
    queryKey: ['student-maic-my-classrooms'],
    queryFn: async () => {
      const res = await maicStudentApi.myClassrooms();
      return res.data;
    },
    enabled: tab === 'mine',
  });

  const handleDelete = async (id: string) => {
    try {
      await maicStudentApi.deleteClassroom(id);
      await deleteStoredClassroom(id);
      queryClient.invalidateQueries({ queryKey: ['student-maic-my-classrooms'] });
    } catch {
      // Silently fail
    }
  };

  const isLoading = tab === 'browse' ? isLoadingBrowse : isLoadingMine;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">AI Classroom</h1>
          <p className="mt-1 text-sm text-gray-500">
            Browse classrooms or create your own AI-powered interactive lessons
          </p>
        </div>
        <button
          onClick={() => navigate('/student/ai-classroom/new')}
          className="inline-flex items-center gap-2 rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 transition-colors"
        >
          <PlusIcon />
          Create
        </button>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200">
        <nav className="flex gap-6" aria-label="Tabs">
          <button
            onClick={() => setTab('browse')}
            className={cn(
              'pb-2.5 text-sm font-medium border-b-2 transition-colors',
              tab === 'browse'
                ? 'border-indigo-600 text-indigo-600'
                : 'border-transparent text-gray-500 hover:text-gray-700',
            )}
          >
            Browse
          </button>
          <button
            onClick={() => setTab('mine')}
            className={cn(
              'pb-2.5 text-sm font-medium border-b-2 transition-colors',
              tab === 'mine'
                ? 'border-indigo-600 text-indigo-600'
                : 'border-transparent text-gray-500 hover:text-gray-700',
            )}
          >
            My Classrooms
          </button>
        </nav>
      </div>

      {/* Search (browse tab only) */}
      {tab === 'browse' && (
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
        </div>
      )}

      {/* Content */}
      {isLoading ? (
        <div className="flex justify-center py-16">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600" />
        </div>
      ) : tab === 'browse' ? (
        classrooms.length === 0 ? (
          <div className="text-center py-16">
            <PresentationIcon />
            <h3 className="mt-4 text-lg font-medium text-gray-900">No classrooms available</h3>
            <p className="mt-2 text-sm text-gray-500">
              Check back later for new AI Classroom sessions from your teachers.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {classrooms.map((c) => (
              <ClassroomCard
                key={c.id}
                classroom={c}
                onClick={() => navigate(`/student/ai-classroom/${c.id}`)}
              />
            ))}
          </div>
        )
      ) : (
        myClassrooms.length === 0 ? (
          <div className="text-center py-16">
            <PresentationIcon />
            <h3 className="mt-4 text-lg font-medium text-gray-900">No classrooms yet</h3>
            <p className="mt-2 text-sm text-gray-500">
              Create your first AI Classroom on any educational topic.
            </p>
            <button
              onClick={() => navigate('/student/ai-classroom/new')}
              className="mt-4 inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 transition-colors"
            >
              <PlusIcon />
              Create Classroom
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {myClassrooms.map((c) => (
              <MyClassroomCard
                key={c.id}
                classroom={c}
                onClick={() => navigate(`/student/ai-classroom/${c.id}`)}
                onDelete={() => handleDelete(c.id!)}
              />
            ))}
          </div>
        )
      )}
    </div>
  );
};
