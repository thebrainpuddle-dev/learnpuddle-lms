// src/pages/teacher/CompetencyPage.tsx
//
// Teacher competency mapping dashboard. Shows skill proficiency levels
// grouped by category, overall competency score, gap indicators, and
// recommended courses to close skill gaps.

import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  AcademicCapIcon,
  ArrowTrendingUpIcon,
  ExclamationTriangleIcon,
  ChevronRightIcon,
  SparklesIcon,
  CheckCircleIcon,
} from '@heroicons/react/24/outline';
import { teacherService } from '../../services/teacherService';
import type {
  CompetencyDashboard,
  CompetencySkill,
  CompetencyCategory,
  CompetencyRecommendation,
} from '../../services/teacherService';
import { usePageTitle } from '../../hooks/usePageTitle';

// ─── Helpers ────────────────────────────────────────────────────────────────

const LEVEL_LABELS = ['Not Assessed', 'Foundational', 'Developing', 'Proficient', 'Advanced', 'Expert'];
const LEVEL_COLORS = [
  'bg-slate-200',
  'bg-sky-400',
  'bg-emerald-400',
  'bg-indigo-500',
  'bg-violet-500',
  'bg-amber-500',
];

function LevelBar({ current, target }: { current: number; target: number }) {
  return (
    <div className="flex items-center gap-2">
      <div className="flex gap-0.5">
        {[1, 2, 3, 4, 5].map((lvl) => (
          <div
            key={lvl}
            className={`h-2 w-5 rounded-sm ${
              lvl <= current
                ? LEVEL_COLORS[current] || 'bg-indigo-500'
                : 'bg-slate-100'
            }`}
          />
        ))}
      </div>
      <span className="text-[11px] font-medium text-slate-500">
        {current}/{target}
      </span>
    </div>
  );
}

function ScoreRing({ value }: { value: number }) {
  const r = 40;
  const c = 2 * Math.PI * r;
  const offset = c - (c * Math.min(value, 100)) / 100;
  const color = value >= 80 ? '#10b981' : value >= 50 ? '#f59e0b' : '#ef4444';

  return (
    <svg width="100" height="100" className="block">
      <circle cx="50" cy="50" r={r} fill="none" stroke="#f1f5f9" strokeWidth="8" />
      <circle
        cx="50"
        cy="50"
        r={r}
        fill="none"
        stroke={color}
        strokeWidth="8"
        strokeLinecap="round"
        strokeDasharray={c}
        strokeDashoffset={offset}
        transform="rotate(-90 50 50)"
        className="transition-all duration-700 ease-out"
      />
      <text x="50" y="50" textAnchor="middle" dominantBaseline="central" className="fill-slate-900 text-lg font-bold">
        {Math.round(value)}%
      </text>
    </svg>
  );
}

function CategoryBar({ category }: { category: CompetencyCategory }) {
  const pct = category.avg_target > 0 ? Math.round((category.avg_current / category.avg_target) * 100) : 0;
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <span className="text-[13px] font-medium text-slate-700">{category.category}</span>
        <span className="text-[11px] text-slate-500">
          {category.avg_current} / {category.avg_target} avg
          {category.gap_count > 0 && (
            <span className="ml-1.5 text-amber-600">({category.gap_count} gap{category.gap_count > 1 ? 's' : ''})</span>
          )}
        </span>
      </div>
      <div className="h-2 rounded-full bg-slate-100 overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${
            pct >= 80 ? 'bg-emerald-500' : pct >= 50 ? 'bg-amber-500' : 'bg-red-400'
          }`}
          style={{ width: `${Math.min(pct, 100)}%` }}
        />
      </div>
    </div>
  );
}

// ─── Page ───────────────────────────────────────────────────────────────────

export const CompetencyPage: React.FC = () => {
  usePageTitle('Competency Map');
  const navigate = useNavigate();

  const { data, isLoading, error } = useQuery<CompetencyDashboard>({
    queryKey: ['teacherCompetency'],
    queryFn: () => teacherService.getCompetencyDashboard(),
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-tp-accent" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="text-center py-20">
        <ExclamationTriangleIcon className="mx-auto h-12 w-12 text-slate-300" />
        <p className="mt-3 text-sm text-slate-500">Could not load competency data.</p>
      </div>
    );
  }

  // Empty state
  if (data.total_skills === 0) {
    return (
      <div className="text-center py-20">
        <AcademicCapIcon className="mx-auto h-16 w-16 text-slate-200" />
        <h2 className="mt-4 text-lg font-semibold text-slate-900">No Skills Mapped Yet</h2>
        <p className="mt-1 text-sm text-slate-500 max-w-md mx-auto">
          Your school administrator hasn&apos;t assigned any competency skills to your profile yet.
          Once skills are mapped, you&apos;ll see your proficiency levels and growth areas here.
        </p>
      </div>
    );
  }

  // Group skills by category for the detail section
  const skillsByCategory: Record<string, CompetencySkill[]> = {};
  for (const skill of data.skills) {
    const cat = skill.category || 'Uncategorised';
    (skillsByCategory[cat] ||= []).push(skill);
  }

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h1 className="text-[22px] font-bold text-slate-900">Competency Map</h1>
        <p className="mt-1 text-[13px] text-slate-500">
          Track your professional skills and identify growth areas
        </p>
      </div>

      {/* ─── Stat Cards ──────────────────────────────────────────── */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard
          label="Competency Score"
          value={`${Math.round(data.overall_score)}%`}
          icon={<SparklesIcon className="h-5 w-5 text-indigo-500" />}
          accent="indigo"
        />
        <StatCard
          label="Total Skills"
          value={data.total_skills}
          icon={<AcademicCapIcon className="h-5 w-5 text-emerald-500" />}
          accent="emerald"
        />
        <StatCard
          label="Skill Gaps"
          value={data.total_gaps}
          icon={<ExclamationTriangleIcon className="h-5 w-5 text-amber-500" />}
          accent="amber"
        />
        <StatCard
          label="Categories"
          value={data.categories.length}
          icon={<ArrowTrendingUpIcon className="h-5 w-5 text-sky-500" />}
          accent="sky"
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* ─── Left column: Score + Category overview ────────────── */}
        <div className="space-y-6 lg:col-span-1">
          {/* Overall Score Ring */}
          <div className="rounded-2xl border border-slate-200 bg-white p-5">
            <h3 className="text-[13px] font-semibold text-slate-500 uppercase tracking-wide mb-4">
              Overall Score
            </h3>
            <div className="flex justify-center">
              <ScoreRing value={data.overall_score} />
            </div>
            <p className="mt-3 text-center text-[12px] text-slate-500">
              {data.overall_score >= 80
                ? 'Excellent — you are meeting most targets'
                : data.overall_score >= 50
                ? 'On track — keep building your skills'
                : 'Getting started — focus on key growth areas'}
            </p>
          </div>

          {/* Category breakdown */}
          <div className="rounded-2xl border border-slate-200 bg-white p-5">
            <h3 className="text-[13px] font-semibold text-slate-500 uppercase tracking-wide mb-4">
              By Category
            </h3>
            <div className="space-y-4">
              {data.categories.map((cat) => (
                <CategoryBar key={cat.category} category={cat} />
              ))}
            </div>
          </div>
        </div>

        {/* ─── Right column: Skills detail + Recommendations ────── */}
        <div className="space-y-6 lg:col-span-2">
          {/* Skills by category */}
          {Object.entries(skillsByCategory).map(([category, skills]) => (
            <div key={category} className="rounded-2xl border border-slate-200 bg-white">
              <div className="border-b border-slate-100 px-5 py-3">
                <h3 className="text-[14px] font-semibold text-slate-900">{category}</h3>
              </div>
              <div className="divide-y divide-slate-100">
                {skills.map((skill) => (
                  <div key={skill.id} className="flex items-center justify-between px-5 py-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <p className="text-[13px] font-medium text-slate-900 truncate">{skill.name}</p>
                        {skill.has_gap && (
                          <span className="inline-flex items-center rounded-full bg-amber-50 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700">
                            Gap
                          </span>
                        )}
                        {!skill.has_gap && skill.current_level >= skill.target_level && skill.current_level > 0 && (
                          <CheckCircleIcon className="h-3.5 w-3.5 text-emerald-500" />
                        )}
                      </div>
                      <p className="text-[11px] text-slate-500 mt-0.5">
                        {LEVEL_LABELS[skill.current_level] || 'N/A'} → Target: {LEVEL_LABELS[skill.target_level] || 'N/A'}
                      </p>
                    </div>
                    <LevelBar current={skill.current_level} target={skill.target_level} />
                  </div>
                ))}
              </div>
            </div>
          ))}

          {/* Recommendations */}
          {data.recommendations.length > 0 && (
            <div className="rounded-2xl border border-slate-200 bg-white">
              <div className="border-b border-slate-100 px-5 py-3">
                <h3 className="text-[14px] font-semibold text-slate-900">Recommended Courses</h3>
                <p className="text-[11px] text-slate-500 mt-0.5">Courses that can help close your skill gaps</p>
              </div>
              <div className="divide-y divide-slate-100">
                {data.recommendations.map((rec, idx) => (
                  <button
                    key={`${rec.course_id}-${rec.skill_name}-${idx}`}
                    type="button"
                    onClick={() => {
                      if (rec.is_assigned) navigate(`/teacher/courses/${rec.course_id}`);
                    }}
                    disabled={!rec.is_assigned}
                    className="w-full flex items-center justify-between px-5 py-3 text-left hover:bg-slate-50 transition-colors disabled:opacity-60 disabled:cursor-default"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="text-[13px] font-medium text-slate-900 truncate">{rec.course_title}</p>
                      <p className="text-[11px] text-slate-500 mt-0.5">
                        Teaches <span className="font-medium text-indigo-600">{rec.skill_name}</span> to level {rec.level_taught}
                        {!rec.is_assigned && <span className="ml-1.5 text-slate-400">(not assigned)</span>}
                      </p>
                    </div>
                    {rec.is_assigned && <ChevronRightIcon className="h-4 w-4 text-slate-400 flex-shrink-0" />}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

// ─── Stat Card ──────────────────────────────────────────────────────────────

function StatCard({
  label,
  value,
  icon,
  accent,
}: {
  label: string;
  value: string | number;
  icon: React.ReactNode;
  accent: string;
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4">
      <div className="flex items-center justify-between mb-2">
        <div className={`rounded-lg bg-${accent}-50 p-2`}>{icon}</div>
      </div>
      <p className="text-xl font-bold text-slate-900">{value}</p>
      <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 mt-1">{label}</p>
    </div>
  );
}
