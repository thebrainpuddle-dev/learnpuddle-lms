// src/pages/student/MAICBrowsePage.tsx
//
// Student browse page for public AI classrooms.

import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { usePageTitle } from '../../hooks/usePageTitle';
import { maicStudentApi } from '../../services/openmaicService';
import type { MAICClassroomMeta } from '../../types/maic';

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

// ─── Main Component ───────────────────────────────────────────────────────────

export const MAICBrowsePage: React.FC = () => {
  usePageTitle('AI Classroom');
  const navigate = useNavigate();

  const [search, setSearch] = useState('');
  const [courseFilter, setCourseFilter] = useState('');

  const { data: classrooms = [], isLoading } = useQuery({
    queryKey: ['student-maic-classrooms', search, courseFilter],
    queryFn: async () => {
      const params: Record<string, string> = {};
      if (search.trim()) params.search = search.trim();
      if (courseFilter) params.course_id = courseFilter;
      const res = await maicStudentApi.listClassrooms(params);
      return res.data;
    },
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">AI Classroom</h1>
        <p className="mt-1 text-sm text-gray-500">
          Browse interactive AI-powered classrooms
        </p>
      </div>

      {/* Search */}
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

      {/* Grid */}
      {isLoading ? (
        <div className="flex justify-center py-16">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600" />
        </div>
      ) : classrooms.length === 0 ? (
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
      )}
    </div>
  );
};
