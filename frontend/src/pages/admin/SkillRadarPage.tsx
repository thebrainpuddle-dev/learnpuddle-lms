// src/pages/admin/SkillRadarPage.tsx
//
// Admin Skill Radar — team-wide competency snapshot per skill.
//
// Renders avg current level vs. avg target level across all teachers
// managed by the current admin, as a Recharts RadarChart. Also surfaces
// top skill gaps, summary stats, and a per-skill breakdown table.
//
// Data source: GET /api/reports/manager/skills-overview/ (see
// `backend/apps/reports/manager_views.py::manager_skills_overview`).

import React, { useMemo, useState } from 'react';
import axios from 'axios';
import { useQuery } from '@tanstack/react-query';
import {
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  Legend,
  ResponsiveContainer,
  Tooltip,
} from 'recharts';
import {
  ChartPieIcon,
  UserGroupIcon,
  ExclamationTriangleIcon,
  AcademicCapIcon,
  ArrowPathIcon,
} from '@heroicons/react/24/outline';
import { Loading } from '../../components/common';
import { Badge } from '../../components/ui/badge';
import { Button } from '../../components/common/Button';
import { skillsService } from '../../services/skillsService';
import type {
  SkillOverviewItem,
  SkillsOverviewResponse,
} from '../../services/skillsService';
import { usePageTitle } from '../../hooks/usePageTitle';

// ── Helpers ──────────────────────────────────────────────────────────────────

/** Pull stable, user-facing error text out of an unknown error. */
function getErrorMessage(err: unknown, fallback: string): string {
  if (axios.isAxiosError(err)) {
    const data = err.response?.data as { detail?: string } | undefined;
    if (data?.detail) return data.detail;
    if (err.message) return err.message;
  }
  if (err instanceof Error) return err.message;
  return fallback;
}

/**
 * Reshape the backend rows into the row-per-skill format Recharts expects
 * for a RadarChart. Each entry becomes one axis on the polygon.
 */
interface RadarRow {
  skill: string;
  current: number;
  target: number;
  fullMark: number;
}

function toRadarRows(items: SkillOverviewItem[]): RadarRow[] {
  return items.map((item) => ({
    skill: item.skill_name,
    current: item.avg_current_level,
    target: item.avg_target_level,
    // Scale the axis to 5 (typical max level) or the largest value seen,
    // whichever is bigger. Prevents the ring from clipping if a tenant
    // uses a higher scale.
    fullMark: Math.max(5, item.avg_target_level, item.avg_current_level),
  }));
}

/** Coverage percentage: share of assessed teachers at or above target. */
function coveragePct(item: SkillOverviewItem): number {
  if (item.teachers_assessed === 0) return 0;
  return Math.round((item.at_or_above_target / item.teachers_assessed) * 100);
}

// ── Page ─────────────────────────────────────────────────────────────────────

export const SkillRadarPage: React.FC = () => {
  usePageTitle('Skill Radar');

  const [category, setCategory] = useState<string>('');

  const query = useQuery<SkillsOverviewResponse>({
    queryKey: ['admin', 'skills-overview', { category }],
    queryFn: () =>
      skillsService.overview(category ? { category } : undefined),
  });

  const categoriesQuery = useQuery<string[]>({
    queryKey: ['admin', 'skill-categories'],
    queryFn: async () => {
      const res = await skillsService.categories();
      return res.data as string[];
    },
  });

  const results = query.data?.results ?? [];
  const summary = query.data?.summary;

  const radarRows = useMemo(() => toRadarRows(results), [results]);

  /** Skills sorted by biggest gap first — used for "focus areas" card. */
  const topGaps = useMemo(() => {
    return [...results]
      .filter((r) => r.below_target > 0)
      .sort((a, b) => {
        const gapA = a.avg_target_level - a.avg_current_level;
        const gapB = b.avg_target_level - b.avg_current_level;
        return gapB - gapA;
      })
      .slice(0, 5);
  }, [results]);

  if (query.isLoading) {
    return <Loading />;
  }

  if (query.isError) {
    return (
      <div className="p-6">
        <div
          role="alert"
          className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-800"
        >
          <div className="flex items-start gap-3">
            <ExclamationTriangleIcon className="h-5 w-5 flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <h3 className="font-semibold">Could not load skills overview</h3>
              <p className="mt-1 text-sm">
                {getErrorMessage(query.error, 'Please try again.')}
              </p>
              <Button
                variant="secondary"
                className="mt-3"
                onClick={() => query.refetch()}
              >
                <ArrowPathIcon className="h-4 w-4 mr-2" />
                Retry
              </Button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <header className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <ChartPieIcon className="h-6 w-6 text-primary-600" />
            Skill Radar
          </h1>
          <p className="text-sm text-slate-600 mt-1">
            Team-wide competency snapshot. Compare average current level
            against average target level per skill.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <label
            htmlFor="skill-category-filter"
            className="text-sm text-slate-600"
          >
            Category
          </label>
          <select
            id="skill-category-filter"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-primary-500 focus:ring-primary-500"
          >
            <option value="">All categories</option>
            {(categoriesQuery.data ?? []).map((cat) => (
              <option key={cat} value={cat}>
                {cat}
              </option>
            ))}
          </select>
        </div>
      </header>

      {/* Summary cards */}
      {summary && (
        <section
          aria-label="Summary stats"
          className="grid grid-cols-1 sm:grid-cols-3 gap-4"
        >
          <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-full bg-primary-50 flex items-center justify-center">
                <AcademicCapIcon className="h-5 w-5 text-primary-600" />
              </div>
              <div>
                <p className="text-xs uppercase tracking-wide text-slate-500">
                  Skills tracked
                </p>
                <p
                  className="text-2xl font-semibold text-slate-900"
                  data-testid="stat-skills-tracked"
                >
                  {summary.total_skills_tracked}
                </p>
              </div>
            </div>
          </div>

          <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-full bg-sky-50 flex items-center justify-center">
                <UserGroupIcon className="h-5 w-5 text-sky-600" />
              </div>
              <div>
                <p className="text-xs uppercase tracking-wide text-slate-500">
                  Teachers assessed
                </p>
                <p
                  className="text-2xl font-semibold text-slate-900"
                  data-testid="stat-teachers"
                >
                  {summary.total_teachers}
                </p>
              </div>
            </div>
          </div>

          <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-full bg-amber-50 flex items-center justify-center">
                <ExclamationTriangleIcon className="h-5 w-5 text-amber-600" />
              </div>
              <div>
                <p className="text-xs uppercase tracking-wide text-slate-500">
                  Total skill gaps
                </p>
                <p
                  className="text-2xl font-semibold text-slate-900"
                  data-testid="stat-gaps"
                >
                  {summary.total_teacher_skill_gaps}
                </p>
              </div>
            </div>
          </div>
        </section>
      )}

      {/* Radar chart + focus areas */}
      <section className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <div className="xl:col-span-2 rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-slate-900">
              Current vs. target levels
            </h2>
            <Badge variant="outline">
              {results.length} skill{results.length === 1 ? '' : 's'}
            </Badge>
          </div>

          {results.length === 0 ? (
            <EmptyRadar />
          ) : (
            <div className="h-[420px]" data-testid="radar-wrapper">
              <ResponsiveContainer width="100%" height="100%">
                <RadarChart data={radarRows}>
                  <PolarGrid stroke="#e2e8f0" />
                  <PolarAngleAxis
                    dataKey="skill"
                    tick={{ fontSize: 11, fill: '#475569' }}
                  />
                  <PolarRadiusAxis
                    angle={30}
                    domain={[0, 5]}
                    tick={{ fontSize: 10, fill: '#94a3b8' }}
                  />
                  <Radar
                    name="Avg current"
                    dataKey="current"
                    stroke="#2563eb"
                    fill="#2563eb"
                    fillOpacity={0.35}
                  />
                  <Radar
                    name="Avg target"
                    dataKey="target"
                    stroke="#f59e0b"
                    fill="#f59e0b"
                    fillOpacity={0.15}
                  />
                  <Legend
                    wrapperStyle={{ fontSize: 12 }}
                    verticalAlign="bottom"
                    height={28}
                  />
                  <Tooltip
                    formatter={(value: number | string) =>
                      typeof value === 'number' ? value.toFixed(2) : value
                    }
                  />
                </RadarChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="text-sm font-semibold text-slate-900 mb-3">
            Focus areas
          </h2>
          {topGaps.length === 0 ? (
            <p className="text-sm text-slate-500">
              No skill gaps right now. The team is at or above target across
              every tracked skill.
            </p>
          ) : (
            <ul className="space-y-3" data-testid="focus-list">
              {topGaps.map((item) => {
                const gap =
                  item.avg_target_level - item.avg_current_level;
                return (
                  <li
                    key={item.skill_id}
                    className="rounded-md border border-slate-100 bg-slate-50 p-3"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="font-medium text-slate-900 truncate">
                          {item.skill_name}
                        </p>
                        <p className="text-xs text-slate-500 truncate">
                          {item.skill_category}
                        </p>
                      </div>
                      <Badge variant="warning">
                        -{gap.toFixed(2)}
                      </Badge>
                    </div>
                    <p className="mt-2 text-xs text-slate-600">
                      {item.below_target} of {item.teachers_assessed}{' '}
                      teacher{item.teachers_assessed === 1 ? '' : 's'} below
                      target
                    </p>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </section>

      {/* Skill breakdown table */}
      <section className="rounded-lg border border-slate-200 bg-white shadow-sm overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-200">
          <h2 className="text-sm font-semibold text-slate-900">
            Skill breakdown
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Per-skill averages and coverage across the team.
          </p>
        </div>
        <div className="overflow-x-auto">
          <table
            className="min-w-full divide-y divide-slate-200"
            data-testid="skill-table"
          >
            <thead className="bg-slate-50">
              <tr>
                <th
                  scope="col"
                  className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-600"
                >
                  Skill
                </th>
                <th
                  scope="col"
                  className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-600"
                >
                  Category
                </th>
                <th
                  scope="col"
                  className="px-5 py-3 text-right text-xs font-semibold uppercase tracking-wide text-slate-600"
                >
                  Avg current
                </th>
                <th
                  scope="col"
                  className="px-5 py-3 text-right text-xs font-semibold uppercase tracking-wide text-slate-600"
                >
                  Avg target
                </th>
                <th
                  scope="col"
                  className="px-5 py-3 text-right text-xs font-semibold uppercase tracking-wide text-slate-600"
                >
                  Coverage
                </th>
                <th
                  scope="col"
                  className="px-5 py-3 text-right text-xs font-semibold uppercase tracking-wide text-slate-600"
                >
                  Below target
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 bg-white">
              {results.length === 0 ? (
                <tr>
                  <td
                    colSpan={6}
                    className="px-5 py-6 text-center text-sm text-slate-500"
                  >
                    No skills have been mapped for your team yet.
                  </td>
                </tr>
              ) : (
                results.map((item) => {
                  const pct = coveragePct(item);
                  return (
                    <tr key={item.skill_id} className="hover:bg-slate-50">
                      <td className="px-5 py-3 text-sm font-medium text-slate-900">
                        {item.skill_name}
                      </td>
                      <td className="px-5 py-3 text-sm text-slate-600">
                        {item.skill_category}
                      </td>
                      <td className="px-5 py-3 text-sm text-right tabular-nums text-slate-900">
                        {item.avg_current_level.toFixed(2)}
                      </td>
                      <td className="px-5 py-3 text-sm text-right tabular-nums text-slate-900">
                        {item.avg_target_level.toFixed(2)}
                      </td>
                      <td className="px-5 py-3 text-sm text-right">
                        <Badge
                          variant={
                            pct >= 80
                              ? 'success'
                              : pct >= 50
                              ? 'warning'
                              : 'destructive'
                          }
                        >
                          {pct}%
                        </Badge>
                      </td>
                      <td className="px-5 py-3 text-sm text-right tabular-nums text-slate-900">
                        {item.below_target}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
};

/** Placeholder panel when the radar has no data. */
const EmptyRadar: React.FC = () => (
  <div
    className="flex h-[420px] flex-col items-center justify-center text-center"
    data-testid="radar-empty"
  >
    <ChartPieIcon className="h-10 w-10 text-slate-300 mb-3" />
    <p className="text-sm font-medium text-slate-700">No skills mapped yet</p>
    <p className="text-xs text-slate-500 max-w-xs mt-1">
      Define skills in the Skills Matrix and assign target levels to teachers
      to populate the radar.
    </p>
  </div>
);

export default SkillRadarPage;
